"""QtWebEngine embeds the real VPS panel. No telemetry calculation here."""
from pathlib import Path
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import (QApplication,QWidget,QLabel,QPushButton,QHBoxLayout,QVBoxLayout,
                              QStackedWidget,QFileDialog,QMessageBox)
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from .gui import ConnectionWindow,secondary
from .branding import CREDIT


class ServerPage(QWebEnginePage):
    def __init__(self,profile,parent):
        super().__init__(profile,parent);self.allowed_origin=''
        # Chromium otherwise paints a white page before/while loading HTML.
        self.setBackgroundColor(QColor('#111315'))
        self.fullScreenRequested.connect(self.fullscreen)

    def acceptNavigationRequest(self,url,kind,is_main):
        # Native app stays on its configured loopback panel.
        return not is_main or url.scheme()=='about' or url.toString().startswith(self.allowed_origin+'/')

    def fullscreen(self,request):
        request.accept()
        if request.toggleOn():self.view_window.showFullScreen()
        else:self.view_window.showNormal()


class ViewerWindow(ConnectionWindow):
    def __init__(self,profile,**kwargs):
        super().__init__(profile,**kwargs)
        self.setWindowTitle('Remote Spotter — споттер');self.resize(1440,960);self.setMinimumSize(900,600)
        self.loaded_origin='';self.pending_cookie=None;self.pending_origin=None
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(180)
        nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,25,12,16);nav.setSpacing(4)
        brand=QLabel('Remote\nSpotter');brand.setStyleSheet('font-size:19px;font-weight:600;padding:0 11px 10px;');nav.addWidget(brand)
        role_label=secondary('СПОТТЕР');role_label.setStyleSheet('color:#B5BBC4;font-size:11px;padding:0 11px 25px;');nav.addWidget(role_label)
        self.nav_buttons=[]
        for name,target in [('Сеанс','top'),('Сектора','sectors'),('Все оверлеи','overlays')]:
            button=QPushButton(name);button.setProperty('nav',True);button.setCheckable(True);button.clicked.connect(lambda checked=False,t=target:self.navigate(t));nav.addWidget(button);self.nav_buttons.append((target,button))
        nav.addStretch()
        credit=secondary(CREDIT);credit.setStyleSheet('color:#B5BBC4;font-size:11px;padding:0 11px 12px;');nav.addWidget(credit)
        diagnostics=QPushButton('Диагностика');diagnostics.setProperty('nav',True);diagnostics.clicked.connect(self.diagnostics);nav.addWidget(diagnostics)
        self.retry=QPushButton('Подключиться');self.retry.clicked.connect(self.connect_session);nav.addWidget(self.retry)
        layout.addWidget(sidebar)
        content=QWidget();column=QVBoxLayout(content);column.setContentsMargins(0,0,0,0);column.setSpacing(0)
        self.banner=QLabel('Подключаемся к серверу…');self.banner.setObjectName('viewerBanner');self.banner.setWordWrap(True);column.addWidget(self.banner)
        self.stack=QStackedWidget();column.addWidget(self.stack)
        waiting=QWidget();wait=QVBoxLayout(waiting);wait.addStretch();self.wait_title=QLabel('Подключаемся к VPS');self.wait_title.setAlignment(Qt.AlignmentFlag.AlignCenter);self.wait_title.setStyleSheet('font-size:24px;font-weight:600;');wait.addWidget(self.wait_title)
        note=secondary('После подключения здесь откроется панель пилота.');note.setAlignment(Qt.AlignmentFlag.AlignCenter);wait.addWidget(note);wait.addStretch();self.stack.addWidget(waiting)
        self.web=QWebEngineView();self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # A named persistent profile keeps panel layout/localStorage, while login
        # cookies remain session-only and are renewed through the native backend.
        # Application ownership guarantees that the profile outlives pages,
        # including asynchronous browser cleanup during window shutdown.
        self.browser_profile=QWebEngineProfile('RemoteSpotterViewer',QApplication.instance())
        self.browser_profile.setPersistentStoragePath(str(self.directory/'web-profile'))
        self.browser_profile.setCachePath(str(self.directory/'web-cache'))
        self.browser_profile.setHttpCacheMaximumSize(32*1024*1024)
        self.browser_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.page=ServerPage(self.browser_profile,self.web);self.page.view_window=self
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,True)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,False)
        self.web.setPage(self.page)
        self.browser_profile.cookieStore().cookieAdded.connect(self.cookie_added)
        self.browser_profile.downloadRequested.connect(self.download)
        self.web.loadFinished.connect(self.loaded);self.stack.addWidget(self.web)
        layout.addWidget(content,1);self.navigate('top')
        self.cookie_timer=QTimer(self);self.cookie_timer.setSingleShot(True);self.cookie_timer.timeout.connect(self.cookie_timeout)
        # Initialize Chromium's cookie manager before injecting the session.
        # Waiting for cookieAdded while the page has never navigated deadlocks
        # on some Qt versions, especially when the web widget is still hidden.
        self.web.setUrl(QUrl('about:blank'))

    def viewer_session(self,event):
        if self.closing:return
        origin=event['origin'];cookies=QNetworkCookie.parseCookies(event['cookie'].encode('ascii'))
        if not cookies:
            self.banner.setText('Не удалось открыть сессию споттера');return
        cookie=cookies[0]
        self.pending_cookie=bytes(cookie.value());self.pending_origin=origin
        self.page.allowed_origin=origin
        self.browser_profile.cookieStore().setCookie(cookie,QUrl(origin+'/'))
        self.cookie_timer.start(5000)

    def cookie_added(self,cookie):
        if self.closing:return
        if bytes(cookie.name())!=b'spotter_session' or bytes(cookie.value())!=self.pending_cookie:return
        self.cookie_timer.stop();origin=self.pending_origin;self.pending_cookie=None
        if self.loaded_origin!=origin:
            self.loaded_origin=origin;self.web.setUrl(QUrl(origin+'/'))
        else:
            # Renewal after 12h does not destroy panel layout/scroll/history.
            self.page.runJavaScript("if(typeof connect==='function')connect();")

    def cookie_timeout(self):
        self.loaded_origin=''
        self.banner.setText('Не удалось передать сессию в панель. Закройте и снова откройте приложение.')

    def loaded(self,ok):
        if self.closing or self.web.url().scheme()=='about':return
        if ok:
            def ready(found):
                if not found or self.closing:return
                self.loaded_origin=self.pending_origin or self.loaded_origin
                self.stack.setCurrentWidget(self.web)
                self.page.runJavaScript("if(typeof connect==='function')connect();")
            self.page.runJavaScript("!!document.getElementById('dashboard')",ready)
        else:
            self.loaded_origin='';self.stack.setCurrentIndex(0)
            self.wait_title.setText('Панель временно недоступна')
            # Retry the document, not only its WebSocket, once VPS returns.

    def show_state(self,state):
        caption=state['title']
        if state['phase']=='online':
            caption=f"{state['partner']} · {state['game_caption']}"
            if state['game']=='live' and not state['data_fresh']:caption+=' · данные устарели'
            if not self.loaded_origin and not self.pending_cookie:
                # Login is renewed by Session on a subsequent attempt. Expose a
                # retry after a document-load failure rather than a blank page.
                self.retry.setEnabled(True)
        self.banner.setText(caption + ((' · '+state['reason']) if state['reason'] else ''))
        self.retry.setEnabled(state['can_connect'] or (state['phase']=='online' and not self.loaded_origin))
        self.retry.setText('Подключено' if state['phase']=='online' else 'Подключиться')
        self.wait_title.setText(state['title'])
        if state['phase']=='online' and not self.loaded_origin and not self.pending_cookie and self.pending_origin:
            self.loaded_origin=self.pending_origin;self.web.setUrl(QUrl(self.pending_origin+'/'))

    def navigate(self,target):
        for name,button in self.nav_buttons:button.setChecked(name==target)
        scripts={
            'top':"window.scrollTo({top:0,behavior:'smooth'});",
            'sectors':"document.querySelector('.timing-panel')?.scrollIntoView({behavior:'smooth'});",
            'overlays':"const advanced=document.getElementById('advanced-panels');if(advanced){advanced.open=true;advanced.scrollIntoView({behavior:'smooth'});}"}
        if self.loaded_origin:self.page.runJavaScript(scripts[target])

    def diagnostics(self):
        s=self.last_state
        text=f"Соединение: {s['title']}\nИгра: {s['game_caption']}\nПартнёр: {s['partner']}\n\nВозраст результата на VPS: {s['source_age_ms']} мс\nВозраст входящих данных: {s['ingest_age_ms']} мс\nРасчёт: {s['compute_ms']:.2f} мс\n\nЖурнал: {self.directory/'viewer.log'}"
        QMessageBox.information(self,'Состояние подключения',text)

    def download(self,item):
        path,_=QFileDialog.getSaveFileName(self,'Сохранить файл',item.downloadFileName())
        if path:
            target=Path(path);item.setDownloadDirectory(str(target.parent));item.setDownloadFileName(target.name);item.accept()
        else:item.cancel()

    def begin_shutdown(self):
        # Hide before stopping/unloading the browser. closeEvent can remain
        # pending while the owned SSH process and worker finish cleanup.
        self.hide()
        self.stack.setCurrentIndex(0)
        super().begin_shutdown()
        self.cookie_timer.stop();self.pending_cookie=None
        self.banner.setText('Завершаем соединение…')
        self.web.stop();self.web.setUrl(QUrl('about:blank'))
