"""Development browser fixture for Playwright when standalone Chromium is absent."""
import os
import sys

os.environ['QTWEBENGINE_REMOTE_DEBUGGING']=sys.argv[1]
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

app=QApplication([])
view=QWebEngineView();view.resize(1920,1080);view.show();view.setUrl(QUrl('about:blank'))
view.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,True)
view.page().fullScreenRequested.connect(lambda request:request.accept())
def download(item):
    item.setDownloadDirectory(os.environ['SPOTTER_QT_DOWNLOAD_DIR']);item.accept()
QWebEngineProfile.defaultProfile().downloadRequested.connect(download)
sys.exit(app.exec())
