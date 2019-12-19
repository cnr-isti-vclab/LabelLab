# TagLab
# A semi-automatic segmentation tool
#
# Copyright(C) 2019
# Visual Computing Lab
# ISTI - Italian National Research Council
# All rights reserved.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License (http://www.gnu.org/licenses/gpl.txt)
# for more details.

import math
import copy
import numpy as np

from skimage import measure
from skimage.util import pad
from scipy import ndimage as ndi
from PyQt5.QtGui import QPainterPath, QPolygonF, QImage, QPixmap, qRgba
from PyQt5.QtCore import QPointF

from skimage.morphology import flood, flood_fill, binary_dilation, binary_erosion
from skimage.measure import points_in_poly
from skimage.draw import polygon_perimeter, polygon
from skimage.filters import gaussian

import source.Mask as Mask
from source import utils


import time

class Blob(object):
    """
    Blob data. A blob is a group of pixels.
    A blob can be tagged with the class and other information.
    Both the set of pixels and the corresponding vectorized version are stored.
    """

    def __init__(self, region, offset_x, offset_y, id):

        if region == None:     # AN EMPTY BLOB IS CREATED..
            self.area = 0.0
            self.perimeter = 0.0
            self.centroid = np.zeros((2))
            self.bbox = np.zeros((4))

            # placeholder; empty contour
            self.contour = np.zeros((2, 2))
            self.inner_contours = []
            self.qpath = None
            self.qpath_gitem = None

            self.instance_name = "noname"
            self.blob_name = "noname"
            self.id = 0

        else:

            # extract properties

            self.centroid = np.array(region.centroid)
            cy = self.centroid[0]
            cx = self.centroid[1]
            self.centroid[0] = cx + offset_x
            self.centroid[1] = cy + offset_y

            # Bounding box (min_row, min_col, max_row, max_col).
            # Pixels belonging to the bounding box are in the half-open
            # interval [min_row, max_row) and [min_col, max_col).
            self.bbox = np.array(region.bbox)

            width = self.bbox[3] - self.bbox[1]
            height = self.bbox[2] - self.bbox[0]

            # BBOX ->  TOP, LEFT, WIDTH, HEIGHT
            self.bbox[0] = self.bbox[0] + offset_y
            self.bbox[1] = self.bbox[1] + offset_x
            self.bbox[2] = width
            self.bbox[3] = height

            # QPainterPath associated with the contours
            self.qpath = None

            # QGraphicsItem associated with the QPainterPath
            self.qpath_gitem = None

            # to extract the contour we use the mask cropped according to the bbox
            input_mask = region.image.astype(int)
            self.contour = np.zeros((2, 2))
            self.inner_contours = []
            self.updateUsingMask(self.bbox, input_mask)

            # a string with a progressive number to identify the instance
            self.instance_name = "coral" + str(id)

            # a string with a number to identify the blob plus its centroid
            xc = int(self.centroid[0])
            yc = int(self.centroid[1])
            self.blob_name = "blob" + str(id) + "-" + str(xc) + "-" + str(yc)
            self.id = id

        # deep extreme points (for fine-tuning)
        self.deep_extreme_points = np.zeros((4, 2))

        # name of the class
        self.class_name = "Empty"

        # color of the class
        self.class_color = [128, 128, 128]

        # note about the coral, i.e. damage type
        self.note = ""

        # QImage corresponding to the current mask
        self.qimg_mask = None

        # QPixmap associated with the mask (for pixel-level editing operations)
        self.pxmap_mask = None

        # QGraphicsItem associated with the pixmap mask
        self.pxmap_mask_gitem = None

        # membership group (if any)
        self.group = None
    def copy(self):
        blob = Blob(None, 0, 0, 0)

        blob.area = self.area
        blob.perimeter = self.perimeter
        blob.centroid = self.centroid
        blob.bbox = self.bbox

        blob.contour = self.contour.copy()
        for inner in self.inner_contours:
            blob.inner_contours.append(inner.copy())
        blob.qpath_gitem = None
        blob.qpath = None

        blob.instance_name = blob.instance_name
        blob.blob_name = self.blob_name
        blob.id = self.id

        blob.class_name = self.class_name

        blob.deep_extreme_points = self.deep_extreme_points

        self.note = ""
        self.qimg_mask = None
        self.pxmap_mask = None
        self.pxmap_mask_gitem = None
        return blob

    def __deepcopy__(self, memo):
        #avoid recursion!
        deepcopy_method = self.__deepcopy__
        self.__deepcopy__ = None
        #save and later restore qobjects
        path = self.qpath
        pathitem = self.qpath_gitem
        #no deep copy for qobjects
        self.qpath = None
        self.qpath_gitem = None

        blob = copy.deepcopy(self)
        blob.contour = self.contour.copy()
        blob.inner_contours.clear()
        for inner in self.inner_contours:
            blob.inner_contours.append(inner.copy())

        blob.qpath = None
        blob.qpath_gitem = None
        self.qpath = path
        self.qpath_gitem = pathitem
        #restore deepcopy (also to the newly created Blob!
        blob.__deepcopy__ = self.__deepcopy__ = deepcopy_method
        return blob

    def setId(self, id):

        # a string with a number to identify the blob plus its centroid
        xc = int(self.centroid[0])
        yc = int(self.centroid[1])
        self.blob_name = "blob" + str(id) + "-" + str(xc) + "-" + str(yc)
        self.id = id

    def getMask(self):
        """
        It creates the mask from the contour and returns it.
        """

        r = self.bbox[3]
        c = self.bbox[2]

        mask = np.zeros((r, c), dtype=np.bool_)

        # main polygon
        [rr, cc] = polygon(self.contour[:, 1], self.contour[:, 0])
        rr = rr - int(self.bbox[0])
        cc = cc - int(self.bbox[1])
        mask[rr, cc] = 1

        # holes
        for inner_contour in self.inner_contours:
            [rr, cc] = polygon(inner_contour[:, 1], inner_contour[:, 0])
            rr = rr - int(self.bbox[0])
            cc = cc - int(self.bbox[1])
            mask[rr, cc] = 0

        return mask


    def updateUsingMask(self, bbox, mask):

        self.bbox = bbox
        self.createContourFromMask(mask)
        self.calculatePerimeter()
        self.calculateCentroid(mask)
        self.calculateArea(mask)

    def lineToPoints(self, lines, snap = False):
        points = np.empty(shape=(0, 2), dtype=int)

        for line in lines:
            p = self.drawLine(line)
            if p.shape[0] == 0:
                continue
            if snap:
                p = self.snapToBorder(p)
            if p is None:
                continue
            points = np.append(points, p, axis=0)
        return points


    def drawLine(self, line):
        (x, y) = utils.draw_open_polygon(line[:, 1], line[:, 0])
        points = np.asarray([x, y]).astype(int)
        points = points.transpose()
        points[:, [1, 0]] = points[:, [0, 1]]
        return points



    def snapToBorder(self, points):
        return self.snapToContour(points, self.contour)


    def snapToContour(self, points, contour):
        """
        Given a curve specified as a set of points, snap the curve on the blob mask:
          1) the initial segments of the curve are removed until they snap
          2) the end segments of the curve are removed until they snap

        """
        test = points_in_poly(points, contour)
        if test is None or test.shape[0] == 0:
            return None
        jump = np.gradient(test.astype(int))
        ind = np.nonzero(jump)
        ind = np.asarray(ind)

        snappoints = None
        if ind.shape[1] > 2:
            first_el = ind[0, 0] + 1
            last_el = ind[0, -1]
            snappoints = points[first_el:last_el, :].copy()

        return snappoints

    def snapToInternalBorders(self, points):
        if not self.inner_contours:
            return None
        snappoints = np.zeros(shape=(0, 2))
        for contour in self.inner_contours:
            snappoints = np.append(snappoints, self.snapToContour(points, contour))
        return snappoints

    def createFromClosedCurve(self, lines):
        """
        It creates a blob starting from a closed curve. If the curve is not closed False is returned.
        If the curve intersect itself many times the first segmented region is created.
        """

        points = self.lineToPoints(lines)

        box = Mask.pointsBox(points, 4)

        (mask, box) = Mask.jointMask(box, box)
        Mask.paintPoints(mask, box, points, 1)
        mask = ndi.binary_fill_holes(mask)
        mask = binary_erosion(mask)
        mask = binary_erosion(mask)
        mask = binary_erosion(mask)
        mask = binary_dilation(mask)
        mask = binary_dilation(mask)
        self.updateUsingMask(box, mask)
        return True


    def createCrack(self, input_arr, x, y, tolerance, preview=True):

        """
        Given a inner blob point (x,y), the function use it as a seed for a paint butcket tool and create
        a correspondent blob hole
        """

        x_crop = x - self.bbox[1]
        y_crop = y - self.bbox[0]

        input_arr = gaussian(input_arr, 2)
        # input_arr = segmentation.inverse_gaussian_gradient(input_arr, alpha=1, sigma=1)

        blob_mask = self.getMask()

        crack_mask = flood(input_arr, (int(y_crop), int(x_crop)), tolerance=tolerance).astype(int)
        cracked_blob = np.logical_and((blob_mask > 0), (crack_mask < 1))
        cracked_blob = cracked_blob.astype(int)

        if not preview:
            self.updateUsingMask(self.bbox, cracked_blob)

        return cracked_blob


    def createContourFromMask(self, mask):
        """
        It creates the contour (and the corrisponding polygon) from the blob mask.
        """

        # NOTE: The mask is expected to be cropped around its bbox (!!) (see the __init__)

        self.inner_contours.clear()

        # we need to pad the mask to avoid to break the contour that touches the borders
        PADDED_SIZE = 2
        img_padded = pad(mask, (PADDED_SIZE, PADDED_SIZE), mode="constant", constant_values=(0, 0))

        contours = measure.find_contours(img_padded, 0.5)

        number_of_contours = len(contours)

        threshold = 20 #min number of points in a small hole

        if number_of_contours > 1:

            # search the longest contour
            npoints_max = 0
            index = 0
            for i, contour in enumerate(contours):
                npoints = contour.shape[0]
                if npoints > npoints_max:
                    npoints_max = npoints
                    index = i

            # divide the contours in OUTER contour and INNER contours
            for i, contour in enumerate(contours):
                if i == index:
                    self.contour = np.array(contour)
                else:
                    if contour.shape[0] > threshold:
                        coordinates = np.array(contour)
                        self.inner_contours.append(coordinates)

            # adjust the coordinates of the outer contour
            # (NOTE THAT THE COORDINATES OF THE BBOX ARE IN THE GLOBAL MAP COORDINATES SYSTEM)
            for i in range(self.contour.shape[0]):
                ycoor = self.contour[i, 0]
                xcoor = self.contour[i, 1]
                self.contour[i, 0] = xcoor - PADDED_SIZE + self.bbox[1]
                self.contour[i, 1] = ycoor - PADDED_SIZE + self.bbox[0]

            # adjust coordinates of the INNER contours
            for j, contour in enumerate(self.inner_contours):
                for i in range(contour.shape[0]):
                    ycoor = contour[i, 0]
                    xcoor = contour[i, 1]
                    self.inner_contours[j][i, 0] = xcoor - PADDED_SIZE + self.bbox[1]
                    self.inner_contours[j][i, 1] = ycoor - PADDED_SIZE + self.bbox[0]

        elif number_of_contours == 1:

            coords = measure.approximate_polygon(contours[0], tolerance=1.2)
            self.contour = np.array(coords)

            # adjust the coordinates of the outer contour
            # (NOTE THAT THE COORDINATES OF THE BBOX ARE IN THE GLOBAL MAP COORDINATES SYSTEM)
            for i in range(self.contour.shape[0]):
                ycoor = self.contour[i, 0]
                xcoor = self.contour[i, 1]
                self.contour[i, 0] = xcoor - PADDED_SIZE + self.bbox[1]
                self.contour[i, 1] = ycoor - PADDED_SIZE + self.bbox[0]
        else:

            print("ZERO CONTOURS -> THERE ARE SOME PROBLEMS HERE !!!!!!)")

    def setupForDrawing(self):
        """
        Create the QPolygon and the QPainterPath according to the blob's contours.
        """

        # QPolygon to draw the blob
        qpolygon = QPolygonF()
        for i in range(self.contour.shape[0]):
            qpolygon << QPointF(self.contour[i, 0], self.contour[i, 1])

        self.qpath = QPainterPath()
        self.qpath.addPolygon(qpolygon)

        for inner_contour in self.inner_contours:
            qpoly_inner = QPolygonF()
            for i in range(inner_contour.shape[0]):
                qpoly_inner << QPointF(inner_contour[i, 0], inner_contour[i, 1])

            path_inner = QPainterPath()
            path_inner.addPolygon(qpoly_inner)
            self.qpath = self.qpath.subtracted(path_inner)

    def createQPixmapFromMask(self):

        w = self.bbox[2]
        h = self.bbox[3]
        self.qimg_mask = QImage(w, h, QImage.Format_ARGB32)
        self.qimg_mask.fill(qRgba(0, 0, 0, 0))

        if self.class_name == "Empty":
            rgba = qRgba(255, 255, 255, 255)
        else:
            rgba = qRgba(self.class_color[0], self.class_color[1], self.class_color[2], 100)

        blob_mask = self.getMask()
        for x in range(w):
            for y in range(h):
                if blob_mask[y, x] == 1:
                    self.qimg_mask.setPixel(x, y, rgba)

        self.pxmap_mask = QPixmap.fromImage(self.qimg_mask)

    def calculateCentroid(self, mask):
        m = measure.moments(mask)
        c = np.array((m[0, 1] / m[0, 0], m[1, 0] / m[0, 0]))

        #centroid is (x, y) while measure returns (y,x and bbox is yx)
        self.centroid  = np.array((c[1] + self.bbox[1], c[0]+ self.bbox[0]))
        self.blob_name = "coral-" + str(self.centroid[0]) + "-" + str(self.centroid[1])

    def calculateContourPerimeter(self, contour):

        #self.perimeter = measure.perimeter(mask) instead?

        # perimeter of the outer contour
        px1 = contour[0, 0]
        py1 = contour[0, 1]
        N = contour.shape[0]
        pxlast = contour[N-1, 0]
        pylast = contour[N-1, 1]
        perim = math.sqrt((px1-pxlast)*(px1-pxlast) + (py1-pylast)*(py1-pylast))
        for i in range(1, contour.shape[0]):
            px2 = contour[i, 0]
            py2 = contour[i, 1]

            d = math.sqrt((px1 - px2)*(px1-px2) + (py1-py2)*(py1-py2))
            perim += d

            px1 = px2
            py1 = py2

        return perim

    def calculatePerimeter(self):

        self.perimeter = self.calculateContourPerimeter(self.contour)

        for contour in self.inner_contours:
            self.perimeter += self.calculateContourPerimeter(self.contour)

    def calculateArea(self, mask):
        self.area = mask.sum().astype(float)



    def fromDict(self, dict):
        """
        Set the blob information given it represented as a dictionary.
        """

        self.bbox = np.asarray(dict["bbox"])

        self.centroid = np.asarray(dict["centroid"])
        self.area = dict["area"]
        self.perimeter = dict["perimeter"]

        self.contour = np.asarray(dict["contour"])
        inner_contours = dict["inner contours"]
        self.inner_contours = []
        for c in inner_contours:
            self.inner_contours.append(np.asarray(c))

        self.deep_extreme_points = np.asarray(dict["deep_extreme_points"])
        self.class_name = dict["class name"]
        self.class_color = dict["class color"]
        self.instance_name = dict["instance name"]
        self.blob_name = dict["blob name"]
        self.id = dict["id"]
        self.note = dict["note"]

        # finalize blob
        #self.setupForDrawing()


    def toDict(self):
        """
        Get the blob information as a dictionary.
        """

        dict = {}

        dict["bbox"] = self.bbox.tolist()

        dict["centroid"] = self.centroid.tolist()
        dict["area"] = self.area
        dict["perimeter"] = self.perimeter

        dict["contour"] = self.contour.tolist()

        dict["inner contours"] = []
        for c in self.inner_contours:
            dict["inner contours"].append(c.tolist())

        dict["deep_extreme_points"] = self.deep_extreme_points.tolist()

        dict["class name"] = self.class_name
        dict["class color"] = self.class_color

        dict["instance name"] = self.instance_name
        dict["blob name"] = self.blob_name
        dict["id"] = self.id
        dict["note"] = self.note

        return dict

