# TagLab
# A semi-automatic segmentation tool
#
# Copyright(C) 2021
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
# GNU General Public License (http://www.gnu.org/licenses/gpl.txt)
# for more details.
from PyQt5.QtCore import Qt, QAbstractTableModel, QItemSelectionModel, QSortFilterProxyModel, QRegExp, QModelIndex,  QSize, \
    pyqtSlot, pyqtSignal, QEvent
from PyQt5.QtWidgets import QWidget, QSizePolicy, QComboBox, QLabel, QTableView, QHeaderView, \
    QHBoxLayout, QVBoxLayout, QAbstractItemView, QStyledItemDelegate, QAction, QMenu, QToolButton, QGridLayout, \
    QLineEdit, QApplication, QLineEdit, QWidget, QSizePolicy, QPushButton
from PyQt5.QtGui import QIcon, QColor, QPixmap, QPainter
from pathlib import Path
import os
import pandas as pd
from source.Blob import Blob

path = Path(__file__).parent.absolute()
imdir = str(path)
imdir = imdir.replace('source', '')

class TableModel(QAbstractTableModel):

    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data

        # load icons
        self.icon_eyeopen = QPixmap(os.path.join(imdir, os.path.join("icons", "eye.png")))
        self.icon_eyeclosed = QPixmap(os.path.join(imdir, os.path.join("icons", "cross.png")))

    def data(self, index, role):

        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter

        if role == Qt.BackgroundRole:
            return QColor(40, 40, 40)

        value = self._data.iloc[index.row(), index.column()]

        if role == Qt.DecorationRole:

            if index.column() == 0:

                if int(value) == 0:
                    pxmap = QPixmap(20, 20)
                    pxmap.fill(Qt.transparent)
                    painter = QPainter(pxmap)
                    painter.drawPixmap(0, 0, 20, 20, self.icon_eyeclosed)
                else:
                    pxmap = QPixmap(20, 20)
                    pxmap.fill(Qt.transparent)
                    painter = QPainter(pxmap)
                    painter.drawPixmap(0, 0, 20, 20, self.icon_eyeopen)

                return pxmap

            if index.column() == 1:
                value = value[1:-1]
                value = value.split(",")
                pxmap = QPixmap(20,20)
                pxmap.fill(QColor(int(value[0]), int(value[1]), int(value[2])))
                return pxmap

        if role == Qt.DisplayRole:

            if index.column() == 0:
                return ""

            if index.column() == 1:
                return ""

            if index.column() == 3:
               txt = int(value)

            # format floating point values
            elif index.column() == 4:
                txt = "{:.1f}".format(value)


            else:
                txt = str(value)

            return txt

        if role == Qt.UserRole:

            if index.column() == 1:

                return str(value)

            return float(value)

    def setData(self, index, value, role):

        if index.isValid() and role == Qt.EditRole:
            self._data.iloc[index.row(), index.column()] = value
        else:
            return False

        return True

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):

        # section is the index of the column/row.
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                head = str(self._data.columns[section])
                if head == "Visibility" or head == "Color":
                    return " "
                return head

            if orientation == Qt.Vertical:
                return str(self._data.index[section])

class QtTableLabel(QWidget):

    # custom signals
    visibilityChanged = pyqtSignal()
    activeLabelChanged = pyqtSignal(str)
    doubleClickLabel = pyqtSignal(str)

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super(QtTableLabel, self).__init__(parent)

        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)

        self.data_table = QTableView()
        self.data_table.setMinimumWidth(400)
        self.data_table.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.data_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.data_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setSortingEnabled(True)

        self.model = None
        self.data = None

        layout = QVBoxLayout()
        layout.addWidget(self.data_table)

        self.setLayout(layout)

        self.project = None
        self.activeImg = None

    def setLabels(self, project, img):

        self.project = project
        self.activeImg = img

        # it works also if there is no active image (i.e. img is None)
        self.data = project.create_labels_table(self.activeImg)

        if self.activeImg is not None:

            # establish UNIQUE connections, otherwise the slots will be called MORE THAN ONE TIME
            # when the signal is emitted

            try:
                self.activeImg.annotations.blobUpdated.connect(self.updateBlob, type=Qt.UniqueConnection)
            except:
                pass

            try:
                self.activeImg.annotations.blobAdded.connect(self.addBlob, type=Qt.UniqueConnection)
            except:
                pass

            try:
                self.activeImg.annotations.blobRemoved.connect(self.removeBlob, type=Qt.UniqueConnection)
            except:
                pass

        self.model = TableModel(self.data)
        self.sortfilter = QSortFilterProxyModel(self)
        self.sortfilter.setSourceModel(self.model)
        self.sortfilter.setSortRole(Qt.UserRole)
        self.data_table.setModel(self.sortfilter)

        self.model.table = self.data_table

        self.data_table.setVisible(False)
        self.data_table.verticalHeader().hide()
        self.data_table.setVisible(True)
        self.data_table.setEditTriggers(QAbstractItemView.DoubleClicked)

        self.data_table.horizontalHeader().setMinimumSectionSize(10)
        self.data_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.data_table.setColumnWidth(0, 25)
        self.data_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.data_table.setColumnWidth(1, 25)
        self.data_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.data_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.data_table.horizontalHeader().showSection(0)
        self.data_table.update()

        # for i,row in self.data.iterrows():
        #     color = row['Color']
        #     btnC = self.createColorButton(color)
        #     self.data_table.setIndexWidget(self.data_table.model().index(i,1), btnC)

        style = "QHeaderView::section { background-color: rgb(40,40,40) }"
        self.data_table.setStyleSheet(style)
        self.data_table.selectionModel().selectionChanged.connect(lambda x: self.selectionChanged.emit())

    def createColorButton(self, color):

        color = color[1:-1]
        color = color.split(",")
        btnC = QPushButton("")
        btnC.setFlat(True)
        r = color[0]
        g = color[1]
        b = color[2]
        text = "QPushButton:flat {background-color: rgb(" + r + "," + g + "," + b + "); border: none ;}"

        btnC.setStyleSheet(text)
        btnC.setAutoFillBackground(True)
        btnC.setFixedWidth(20)
        btnC.setFixedHeight(20)

        return btnC

    def clear(self):

        self.model = None
        self.data = None

        self.data_table.setModel(self.model)
        self.data_table.update()

    def updateData(self):

        self.data_table.update()

    def updateTable(self, data_table):

        if self.model is None:
            return

        self.sortfilter.beginResetModel()
        self.model.beginResetModel()

        self.model._data = data_table

        self.sortfilter.endResetModel()
        self.model.endResetModel()

        self.data_table.horizontalHeader().showSection(0)
        self.data_table.update()


    def selectRows(self, rows):
        self.data_table.clearSelection()

        indexes = [self.sortfilter.mapFromSource(self.model.index(r, 0)) for r in rows]
        mode = QItemSelectionModel.Select | QItemSelectionModel.Rows
        for index in indexes:
            self.data_table.selectionModel().select(index, mode)

        if len(rows) > 0:
            value = self.data_table.horizontalScrollBar().value()
            column = self.data_table.columnAt(value)
            self.data_table.scrollTo(self.data_table.model().index(indexes[0].row(), column))


    def eventFilter(self, object, event):

        if type(object) == QLineEdit and event.type() == QEvent.FocusIn :

            self.highlightSelectedLabel(object)

            return False

        if type(object) == QLineEdit and event.type() == QEvent.MouseButtonDblClick :

            label_name = object.text()
            self.doubleClickLabel.emit(label_name)

        return False


    def setAllVisible(self):

        # update the table data
        for row in self.data.rows:
            row['Visibility'] = 1

        # update the labels
        for label in self.labels.values():
            label.visible = True

        # update the table view
        self.data_table.update()

    def setAllNotVisible(self):

        # update the table data
        for row in self.data.rows:
            row['Visibility'] = 0

        # update the labels
        for label in self.labels.values():
            label.visible = True

        # update the table view
        self.data_table.update()

    @pyqtSlot()
    def toggleVisibility(self):

        button_clicked = self.sender()
        key = button_clicked.property('key')
        label = self.labels[key]

        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.setAllNotVisible()
            label.visible = True

        elif QApplication.keyboardModifiers() == Qt.ShiftModifier:
            self.setAllVisible()
            label.visible = False

        else:
            label.visible = not label.visible

        button_clicked.setIcon(self.icon_eyeopen if label.visible is True else self.icon_eyeclosed)

        self.visibilityChanged.emit()

    def highlightSelectedLabel(self, lbl_clicked):

        # reset the text of all the clickable labels
        for lbl in self.lineeditClass:
            lbl.setText(lbl.text())
            lbl.setStyleSheet("QLineEdit { border: none; font-weight: normal; color : lightgray;}")
            lbl.setReadOnly(True)

        txt = lbl_clicked.text()
        lbl_clicked.setText(txt)
        lbl_clicked.setReadOnly(True)
        lbl_clicked.setStyleSheet("QLineEdit { border: 1 px; font-weight: bold; color : white;}")

        self.active_label_name = lbl_clicked.property('key')
        self.activeLabelChanged.emit(self.active_label_name)

    def isClassVisible(self, key):

        return self.labels[key].visible

    def getActiveLabelName(self):

        return self.active_label_name






