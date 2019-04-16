import sys
from os import path
from datetime import datetime
from fnmatch import fnmatch
from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, \
    QFileDialog, QMenu, QMessageBox

import matplotlib
matplotlib.use("agg")
from matplotlib.backends.backend_qt5agg \
    import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib import colors

from rian_iono import RianIono

from filelist import FileList

DATE_TIME_FORMAT = 'yyyy-MM-dd hh:mm'


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.program_name = 'IonoViewie'
        self.file_name = ''
        self.iono = None
        self.ax = None
        self.f2_scatter = None
        self.f1_scatter = None
        self.e_scatter = None
        self.f2_critical = None
        self.f1_critical = None
        self.e_critical = None

        uic.loadUi('./ui/MainWnd.ui', self)

        actions = {
            self.actionExit: sys.exit,
            self.actionOpen: self.open_file_dialog,
            self.actionSave: self.save_file,
            self.actionNext: self.open_next_file,
            self.actionPrevious: self.open_prev_file,
            self.actionFirst: self.open_first_file,
            self.actionLast: self.open_last_file,
            self.actionReload: self.reopen_file,
            self.actionChangeLayer: self.change_layer,
            self.actionClose: self.close_file}
        for key, action in actions.items():
            key.triggered.connect(action)

        self.change_mode(0)  # F2
        self.radioButtonF2.toggled.connect(lambda: self.change_mode(0))
        self.radioButtonF1.toggled.connect(lambda: self.change_mode(1))
        self.radioButtonE.toggled.connect(lambda: self.change_mode(2))

        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        self.horizontalLayout.addWidget(self.canvas)
        self.is_cross = False
        self.canvas.mpl_connect('button_press_event', self.onclick)
        self.canvas.mpl_connect('motion_notify_event', self.onmove)

        listWidgets = [self.listWidgetE, self.listWidgetF1, self.listWidgetF2]
        for w in listWidgets:
            w.setContextMenuPolicy(Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(self.delete_menu)

        spinBoxes = [
            self.doubleSpinBoxF2, self.doubleSpinBoxF1, self.doubleSpinBoxE]
        for w in spinBoxes:
            w.valueChanged.connect(self.plot_lines)

        self.clear_all()

        self.setWindowTitle(self.program_name)
        self.showMaximized()

    def png_state_changed(self, state):
        s = state == Qt.Checked
        elements = [
            self.pngDefaultButton, self.pngWidthSpinBox,
            self.pngHeightSpinBox, self.pngDpiSpinBox]
        for e in elements:
            e.setEnabled(s)

    def change_layer(self):
        mode = self.mode+1 if self.mode < 2 else 0
        if mode == 0:
            self.radioButtonF2.setChecked(True)
        elif mode == 1:
            self.radioButtonF1.setChecked(True)
        elif mode == 2:
            self.radioButtonE.setChecked(True)

    def clear_all(self):
        self.e_scatter = None
        self.f1_scatter = None
        self.f2_scatter = None

        self.e_critical = None
        self.f1_critical = None
        self.f2_critical = None

        self.iono = None
        self.file_name = None

        self.change_mode(0)

        self.doubleSpinBoxF2.setValue(0)
        self.doubleSpinBoxF1.setValue(0)
        self.doubleSpinBoxE.setValue(0)

        self.listWidgetE.clear()
        self.listWidgetF1.clear()
        self.listWidgetF2.clear()

        self.radioButtonF2.setChecked(True)

    def delete_menu(self, point):
        if self.sender().count():
            listMenu = QMenu()
            delete_action = listMenu.addAction('Delete')
            delete_all_action = listMenu.addAction('Delete all')
            point_global = self.sender().mapToGlobal(point)
            r = listMenu.exec_(point_global)
            if r is delete_action:
                item = self.sender().row(self.sender().itemAt(point))
                self.sender().takeItem(item)
            elif r is delete_all_action:
                self.sender().clear()
            self.plot_scatters()

    def change_mode(self, mode):
        self.mode = mode

        widgets = [
            self.doubleSpinBoxE, self.doubleSpinBoxF1, self.doubleSpinBoxF2,
            self.listWidgetE, self.listWidgetF1, self.listWidgetF2]
        for w in widgets:
            w.setEnabled(False)

        if mode == 0:
            self.doubleSpinBoxF2.setEnabled(True)
            self.listWidgetF2.setEnabled(True)
        elif mode == 1:
            self.doubleSpinBoxF1.setEnabled(True)
            self.listWidgetF1.setEnabled(True)
        elif mode == 2:
            self.doubleSpinBoxE.setEnabled(True)
            self.listWidgetE.setEnabled(True)

    def onclick(self, event):
        if event.ydata and event.xdata:
            f = round(self.iono.coord_to_freq(event.xdata), 2)
            h = event.ydata
            s = '{:5.2f} {:5.1f}'.format(f, h)
            if event.button == 1:
                if self.mode == 0:  # F2
                    self.listWidgetF2.addItem(s)
                elif self.mode == 1:  # F1
                    self.listWidgetF1.addItem(s)
                elif self.mode == 2:  # E
                    self.listWidgetE.addItem(s)
            elif event.button == 3:
                if self.mode == 0:  # F2
                    self.doubleSpinBoxF2.setValue(f)
                elif self.mode == 1:  # F1
                    self.doubleSpinBoxF1.setValue(f)
                elif self.mode == 2:  # E
                    self.doubleSpinBoxE.setValue(f)
            elif event.button == 2:
                if self.mode == 0:  # F2
                    self.doubleSpinBoxF2m.setValue(f)
                elif self.mode == 1:  # F1
                    self.doubleSpinBoxF1m.setValue(f)
                elif self.mode == 2:  # E
                    self.doubleSpinBoxEm.setValue(f)
            self.plot_scatters()

    def plot_scatters(self):
        if self.e_scatter is not None:
            self.e_scatter.remove()

        x_e = []
        y_e = []
        for i in range(self.listWidgetE.count()):
            t = self.listWidgetE.item(i).text().split()
            x_e.append(self.iono.freq_to_coord(t[0]))
            y_e.append(float(t[1]))
        self.e_scatter = self.ax.scatter(x_e, y_e, c='g')

        if self.f1_scatter is not None:
            self.f1_scatter.remove()

        x_f1 = []
        y_f1 = []
        for i in range(self.listWidgetF1.count()):
            t = self.listWidgetF1.item(i).text().split()
            x_f1.append(self.iono.freq_to_coord(t[0]))
            y_f1.append(float(t[1]))
        self.f1_scatter = self.ax.scatter(x_f1, y_f1, c='c')

        if self.f2_scatter is not None:
            self.f2_scatter.remove()

        x_f2 = []
        y_f2 = []
        for i in range(self.listWidgetF2.count()):
            t = self.listWidgetF2.item(i).text().split()
            x_f2.append(self.iono.freq_to_coord(t[0]))
            y_f2.append(float(t[1]))
        self.f2_scatter = self.ax.scatter(x_f2, y_f2, c='r')

        self.canvas.draw()

    def plot_lines(self, text):

        if self.iono is None:
            return

        left = self.iono.get_extent()[0]
        right = self.iono.get_extent()[1]
        top = self.iono.get_extent()[3]
        bottom = self.iono.get_extent()[2]

        def plot_line(box, line, color, style='-'):
            if line is not None:
                line.remove()
                line = None
            freq = box.value()
            if freq > 0:
                f = self.iono.freq_to_coord(freq)
                if (f > left) and (f < right):
                    line, = self.ax.plot(
                        [f, f],
                        [bottom, top],
                        c=color,
                        linestyle=style)
                return line

        self.f2_critical = plot_line(
            self.doubleSpinBoxF2, self.f2_critical, 'r')
        self.f1_critical = plot_line(
            self.doubleSpinBoxF1, self.f1_critical, 'c')
        self.e_critical = plot_line(
            self.doubleSpinBoxE, self.e_critical, 'g')

        self.canvas.draw()

    def onmove(self, event):
        if event.ydata and event.xdata:
            f = self.iono.coord_to_freq(event.xdata)
            h = event.ydata
            self.statusbar.showMessage('f={:5.2f}  h\'={:5.1f}'.format(f, h))
            if not self.is_cross:
                QApplication.setOverrideCursor(Qt.CrossCursor)
                self.is_cross = True
        else:
            self.statusbar.showMessage('')
            if self.is_cross:
                QApplication.restoreOverrideCursor()
                self.is_cross = False

    def open_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self)
        self.open_file(file_name)

    def close_file(self):
        self.clear_all()
        self.iono = None
        self.file_name = ''
        self.figure.clear()
        self.ax = None
        self.canvas.draw()

    def open_file(self, file_name):

        self.close_file()

        self.setWindowTitle(self.program_name)

        pattern = '????????_????_iono.ion'

        if file_name and fnmatch(path.split(file_name)[-1], pattern):
            self.clear_all()

            self.iono = RianIono()

            self.iono.load(file_name)
            data = self.iono.get_data()
            if data:

                self.file_name = file_name

                self.ax = self.figure.add_subplot(111)

                extent = self.iono.get_extent()

                cmap = colors.ListedColormap([
                    '#6E1E5A', '#782064', '#8C189A',
                    '#FFFFFF',
                    '#515151', '#474747', '#000000'])

                self.ax.imshow(data, cmap=cmap, interpolation='nearest',
                                   extent=extent, aspect='auto')

                tics = self.iono.get_freq_tics()
                labels = self.iono.get_freq_labels()
                self.ax.set_xticks(tics)
                self.ax.set_xticklabels(labels)

                plt.tight_layout()
                self.setWindowTitle(self.program_name + " - " + file_name)
                self.canvas.draw()

                self.load_text_info()

    def open_next_file(self):
        if self.file_name:
            directory = path.dirname(self.file_name)
            filenames = self.get_filelist(directory)
            index = filenames.index(path.basename(self.file_name))
            if index + 1 < len(filenames):
                new_file_name = path.join(directory, filenames[index + 1])
                self.open_file(new_file_name)

    def open_prev_file(self):
        if self.file_name:
            directory = path.dirname(self.file_name)
            filenames = self.get_filelist(directory)
            index = filenames.index(path.basename(self.file_name))
            if index - 1 >= 0:
                new_file_name = path.join(directory, filenames[index - 1])
                self.open_file(new_file_name)

    def open_last_file(self):
        if self.file_name:
            directory = path.dirname(self.file_name)
            filenames = self.get_filelist(directory)
            new_file_name = path.join(directory, filenames[-1])
            self.open_file(new_file_name)

    def open_first_file(self):
        if self.file_name:
            directory = path.dirname(self.file_name)
            filenames = self.get_filelist(directory)
            new_file_name = path.join(directory, filenames[0])
            self.open_file(new_file_name)

    def reopen_file(self):
        if self.file_name:
            self.open_file(self.file_name)

    def get_filelist(self, directory):
        result = []
        for filename in FileList.get(directory):
            if fnmatch(filename, '????????_????_iono.ion'):
                result.append(filename)
        return result

    def load_text_info(self):
        try:
            with open(self.file_name + '.STD', 'r') as file:

                file.readline()  # read description

                (self.iono.lat, self.iono.long,
                 self.iono.gyro, self.iono.dip,
                 self.iono.sunspot) = file.readline().strip().split()
                date = file.readline().strip()

                foE = float(file.readline().strip())
                if abs(foE - 99.0) > 1:
                    self.doubleSpinBoxE.setValue(foE)
                while True:
                    line = file.readline().strip()
                    if line == 'END':
                        break
                    s = line.split()
                    line = '{:-5.2f} {:-5.1f}'.format(float(s[0]), float(s[1]))
                    self.listWidgetE.addItem(line)

                foF1 = float(file.readline().strip())
                if abs(foF1 - 99.0) > 1:
                    self.doubleSpinBoxF1.setValue(foF1)
                while True:
                    line = file.readline().strip()
                    if line == 'END':
                        break
                    s = line.split()
                    line = '{:-5.2f} {:-5.1f}'.format(float(s[0]), float(s[1]))
                    self.listWidgetF1.addItem(line)

                foF2 = float(file.readline().strip())
                if abs(foF2 - 99.0) > 1:
                    self.doubleSpinBoxF2.setValue(foF2)
                while True:
                    line = file.readline().strip()
                    if line == 'END':
                        break
                    s = line.split()
                    line = '{:-5.2f} {:-5.1f}'.format(float(s[0]), float(s[1]))
                    self.listWidgetF2.addItem(line)

            self.plot_scatters()

        except IOError:
            return

    def save_file(self):
        if self.file_name:
            self.save_std(self.file_name + '.STD')
            self.save_image(self.file_name + '.png')
            self.statusbar.showMessage('File is saved.')

    def save_std(self, filename):

        foE = self.doubleSpinBoxE.value()
        if abs(foE - 99.0) < 1.0 or abs(foE) < 0.1:
            foE = '99.0'

        fohE = ''
        for i in range(self.listWidgetE.count()):
                fohE += self.listWidgetE.item(i).text() + '\n'

        foF1 = self.doubleSpinBoxF1.value()
        if abs(foF1 - 99.0) < 1.0 or abs(foF1) < 0.1:
            foF1 = '99.0'

        fohF1 = ''
        for i in range(self.listWidgetF1.count()):
            fohF1 += self.listWidgetF1.item(i).text() + '\n'

        foF2 = self.doubleSpinBoxF2.value()
        if abs(foF2 - 99.0) < 1.0 or abs(foF2) < 0.1:
            foF2 = '99.0'

        fohF2 = ''
        for i in range(self.listWidgetF2.count()):
            fohF2 += self.listWidgetF2.item(i).text() + '\n'

        def get_value(widget):
            value = 0
            try:
                value = float(widget.text().strip())
            except ValueError:
                pass
            return value

        coordinates = str.format(
            '{} {} {} {} {}',
            str(self.iono.get_lat()),
            str(self.iono.get_lon()),
            str(self.iono.gyro),
            str(self.iono.dip),  # TODO replace
            str(self.iono.sunspot)) # TODO replace

        date = self.iono.get_date().strftime('%Y %m %d %H %M 00')

        station = self.iono.get_station_name()

        with open(filename, 'w') as file:
            file.write(station + '\n')

            file.write(coordinates + '\n')

            file.write(date + '\n')

            file.write(str(foE) + '\n')
            file.write(str(fohE))
            file.write('END\n')

            file.write(str(foF1) + '\n')
            file.write(str(fohF1))
            file.write('END\n')

            file.write(str(foF2) + '\n')
            file.write(str(fohF2))
            file.write('END\n')

    def save_image(self, filename, **kwargs):
        width = 10 if 'width' not in kwargs else kwargs['width']
        height = 6 if 'height' not in kwargs else kwargs['height']
        dpi = 100 if 'dpi' not in kwargs else kwargs['dpi']
        old_size = self.figure.get_size_inches()
        self.figure.set_size_inches(width, height)
        plt.title(self.get_description())
        plt.tight_layout()
        self.figure.savefig(filename, dpi=dpi)
        plt.title('')
        self.figure.set_size_inches(old_size)
        plt.tight_layout()
        self.canvas.draw()

    def get_description(self):
        description = '{}, {}'.format(
            self.iono.get_station_name(),
            self.iono.get_date())
        return description


if __name__ == '__main__':
    app = QApplication(sys.argv)

    main = MainWindow()
    main.show()

    sys.exit(app.exec_())
