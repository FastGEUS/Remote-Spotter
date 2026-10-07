"""Native pilot GUI, viewer shell, and one-time local connection setup."""
import asyncio
import contextlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QLockFile, QCoreApplication, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QFileDialog, QMessageBox,
    QStackedWidget, QFrame, QComboBox)

from . import VERSION
from .branding import CREDIT,icon_path,windows_identity
from .config import Profile, data_dir, load_startup_profile, save_profile, imported_pilot_token
from .session import Session
from .state import State
from .tunnel import scan_host, prepare_hosts, TunnelError

STYLE = '''
QWidget {background:#111315;color:#F2F3F5;font-family:"Segoe UI";font-size:13px;}
QDialog {background:#191C20;}
QLabel[secondary="true"] {color:#B5BBC4;}
QPushButton {background:#23272D;border:1px solid #353B43;border-radius:5px;padding:8px 12px;}
QPushButton:hover {background:#2C3138;}
QPushButton:focus {border:1px solid #DC5A57;}
QPushButton[primary="true"] {background:#DC5A57;color:#111315;border:1px solid #DC5A57;font-weight:600;}
QPushButton[primary="true"]:hover {background:#E67572;}
QPushButton:disabled {background:#191C20;color:#B5BBC4;border:1px solid #353B43;}
QLineEdit {background:#23272D;color:#F2F3F5;border:1px solid #353B43;border-radius:5px;padding:8px;}
QLineEdit:focus {border-color:#DC5A57;}
QFrame#pilotFrame {border:1px solid #353B43;}
QWidget#pilotTitle {border-bottom:1px solid #353B43;}
QPushButton[windowButton="true"] {background:transparent;border:0;border-radius:0;padding:0;font-size:18px;}
QPushButton[windowButton="true"]:hover {background:#23272D;}
QPushButton#closeWindow:hover {background:#DC5A57;color:#111315;}
QWidget#sidebar {background:#191C20;border-right:1px solid #353B43;}
QPushButton[nav="true"] {text-align:left;border:0;background:transparent;padding:11px 12px;}
QPushButton[nav="true"]:checked {background:#23272D;border-left:2px solid #DC5A57;border-radius:0;}
QLabel#viewerBanner {background:#191C20;border-bottom:1px solid #353B43;padding:10px 16px;}
'''


def secondary(text=''):
    widget = QLabel(text)
    widget.setProperty('secondary', True)
    return widget


class Backend(QThread):
    event = Signal(object)

    def __init__(self, profile, directory, demo=False, parent=None):
        super().__init__(parent)
        self.profile, self.directory, self.demo = profile, directory, demo
        self.loop = self.task = None
        self.stop_requested = False

    def run(self):
        try:
            session = Session(self.profile, self.directory, self.event.emit, demo=self.demo)
            self.run_operation(session.run())
        except Exception:
            logging.exception('Desktop backend failed')
            state=State(self.profile.role,phase='error').presentation()
            self.event.emit({'kind':'state',**state})
            self.event.emit({'kind':'error','code':'internal',
                'message':'Не удалось запустить соединение. Подробности сохранены в журнале приложения.'})
        finally:
            self.loop = self.task = None

    def run_operation(self, operation):
        async def execute():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.create_task(operation)
            if self.stop_requested:
                self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                return await self.task
        return asyncio.run(execute())

    def stop(self):
        if self.stop_requested:
            return  # A second cancel would interrupt SSH/collector cleanup.
        self.stop_requested = True
        loop, task = self.loop, self.task
        if loop and task:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass


class Setup(QDialog):
    def __init__(self, role, parent=None, current=None):
        super().__init__(parent)
        self.role, self.profile = role, None
        self.setWindowTitle('Remote Spotter — подключение к VPS')
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        heading = QLabel('Первое подключение')
        heading.setStyleSheet('font-size:22px;font-weight:600;')
        layout.addWidget(heading)
        explanation = secondary('Сохраним доступ на этом компьютере. При следующих запусках вводить ключи не потребуется.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self.host = QLineEdit(current.host if current else '')
        self.user = QLineEdit(current.user if current else 'root')
        self.key = QLineEdit(current.ssh_key if current else str(Path.home()/'.ssh/lmu_spotter'))
        self.token = QLineEdit(current.token if current else '')
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        key_box = QWidget(); key_layout = QHBoxLayout(key_box); key_layout.setContentsMargins(0,0,0,0)
        key_layout.addWidget(self.key)
        browse = QPushButton('Выбрать'); browse.clicked.connect(self.browse_key); key_layout.addWidget(browse)
        form.addRow('VPS',self.host);form.addRow('Пользователь SSH',self.user);form.addRow('Приватный SSH-ключ',key_box)
        form.addRow('Ключ пилота' if role=='pilot' else 'Ключ споттера',self.token)
        self.game=QComboBox()
        for label,value in [('Автоматически: iRacing / LMU','auto'),('iRacing','iracing'),('Le Mans Ultimate','lmu')]:self.game.addItem(label,value)
        self.game.setCurrentIndex(self.game.findData(current.game if current else 'auto'))
        if role=='pilot':form.addRow('Игра',self.game)
        layout.addLayout(form)
        if role=='pilot':
            migrate=QPushButton('Импортировать прежний профиль пилота')
            migrate.clicked.connect(self.import_profile);layout.addWidget(migrate)
            legacy=Path(__file__).resolve().parents[1]/'local-config.json'
            if legacy.exists() and not current:
                try:self.token.setText(imported_pilot_token(legacy))
                except (OSError,ValueError):pass
        self.problem = QLabel();self.problem.setWordWrap(True);self.problem.setStyleSheet('color:#DC5A57;')
        layout.addWidget(self.problem)
        actions=QHBoxLayout();actions.addStretch()
        cancel=QPushButton('Отмена');cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        save=QPushButton('Сохранить');save.setProperty('primary',True);save.clicked.connect(self.save);actions.addWidget(save)
        layout.addLayout(actions)
        self.current=current

    def browse_key(self):
        path,_=QFileDialog.getOpenFileName(self,'Приватный SSH-ключ',str(Path.home()/'.ssh'))
        if path:self.key.setText(path)

    def import_profile(self):
        path,_=QFileDialog.getOpenFileName(self,'Прежний remote/local-config.json','','JSON (*.json)')
        if path:
            try:self.token.setText(imported_pilot_token(path));self.problem.clear()
            except (ValueError,OSError,AttributeError):self.problem.setText('Не удалось прочитать ключ пилота из этого файла.')

    def save(self):
        try:
            self.profile=Profile(role=self.role,token=self.token.text(),ssh_key=self.key.text(),
                host=self.host.text().strip(),user=self.user.text().strip(),
                ssh_port=self.current.ssh_port if self.current else 22,
                server_port=self.current.server_port if self.current else 8080).validate()
            self.profile.game=self.game.currentData()
            save_profile(self.profile)
            self.accept()
        except (ValueError,OSError,RuntimeError):
            self.problem.setText('Проверьте адрес, приватный SSH-ключ и ключ выбранной роли. Сохранение выполняется средствами Windows.')


class HostScan(Backend):
    result = Signal(object)
    def __init__(self,profile,parent=None):super().__init__(profile,None,parent=parent)
    def run(self):
        try:
            value=self.run_operation(scan_host(self.profile))
            if not self.stop_requested:self.result.emit({'value':value})
        except TunnelError as exc:
            logging.warning('SSH host verification failed: %s', exc)
            if not self.stop_requested:self.result.emit({'error':str(exc)})
        except OSError:
            logging.exception('Cannot launch SSH host probe')
            if not self.stop_requested:self.result.emit({'error':'Не удалось запустить OpenSSH для проверки VPS. Проверьте установку Клиента OpenSSH Windows.'})
        except Exception:
            logging.exception('SSH host probe failed')
            if not self.stop_requested:self.result.emit({'error':'Не удалось проверить SSH-ключ VPS. Подробности сохранены в журнале приложения.'})
        finally:self.loop=self.task=None


class ConnectionWindow(QWidget):
    closed = Signal()
    shutdown_started = Signal()
    shutdown_timeout = Signal()
    def __init__(self,profile,*,directory=None,demo=False):
        super().__init__()
        self.profile=profile;self.directory=Path(directory or data_dir());self.demo=demo
        self.worker=None;self.scan=None;self.closing=False;self.last_state=State(profile.role).presentation()
        self.shutdown_poll=QTimer(self);self.shutdown_poll.setInterval(50)
        self.shutdown_poll.timeout.connect(self.finish_shutdown)
        self.shutdown_deadline=QTimer(self);self.shutdown_deadline.setSingleShot(True)
        self.shutdown_deadline.timeout.connect(self.shutdown_timeout.emit)

    def connect_session(self):
        if self.closing:return
        if self.worker and self.worker.isRunning():return
        self.worker=Backend(self.profile,self.directory,self.demo,self)
        self.worker.event.connect(self.backend_event)
        self.worker.finished.connect(self.backend_finished)
        self.worker.start()

    def backend_finished(self):
        if self.closing:QTimer.singleShot(0,self.close)

    def backend_event(self,event):
        if self.closing:return
        if event['kind']=='state':
            self.last_state=event;self.show_state(event)
        elif event['kind']=='error':
            if event['code']=='host-trust':
                self.scan=HostScan(self.profile,self);self.scan.result.connect(self.trust_host);self.scan.start()
            else:
                message=QMessageBox(self);message.setWindowTitle('Remote Spotter');message.setText(event['message'])
                repair=message.addButton('Исправить доступ',QMessageBox.ButtonRole.ActionRole)
                message.addButton(QMessageBox.StandardButton.Close);message.exec()
                if message.clickedButton()==repair:
                    setup=Setup(self.profile.role,self,current=self.profile)
                    if setup.exec()==QDialog.DialogCode.Accepted:self.profile=setup.profile
                # Pilot stays on the single-action window; viewer can retry too.
        elif event['kind']=='viewer-session':self.viewer_session(event)

    def trust_host(self,result):
        if self.closing:return
        if 'error' in result:QMessageBox.warning(self,'Remote Spotter',result['error']);return
        line,fingerprint=result['value']
        choice=QMessageBox.question(self,'Первое подключение к VPS',
            f'Сервер {self.profile.host}\n\nSSH-ключ ED25519:\n{fingerprint}\n\nСверьте отпечаток с сервером. Доверять этому ключу?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if choice==QMessageBox.StandardButton.Yes:
            hosts,_=prepare_hosts(self.directory)
            with hosts.open('a',encoding='utf-8') as file:file.write('\n'+line+'\n')
            self.connect_session()

    def closeEvent(self,event):
        if not self.closing:
            self.closing=True
            self.shutdown_started.emit()
            self.begin_shutdown()
            self.setEnabled(False)
            for thread in (self.worker,self.scan):
                if thread and thread.isRunning():thread.stop()
        active=self.worker and self.worker.isRunning()
        scanning=self.scan and self.scan.isRunning()
        if active or scanning:
            event.ignore()
            if not self.shutdown_deadline.isActive():self.shutdown_deadline.start(6000)
            self.shutdown_poll.start()
            return
        self.shutdown_poll.stop();self.shutdown_deadline.stop()
        event.accept()
        self.closed.emit()

    def begin_shutdown(self):
        for dialog in self.findChildren(QDialog):dialog.reject()
        if hasattr(self,'title'):self.title.setText('Завершаем…')
        if hasattr(self,'connect_button'):self.connect_button.setText('Отключаемся…')

    def finish_shutdown(self):
        if not any(thread and thread.isRunning() for thread in (self.worker,self.scan)):
            self.close()


class PilotTitle(QWidget):
    def __init__(self,parent):
        super().__init__(parent);self.setObjectName('pilotTitle');self.setFixedHeight(36)
        layout=QHBoxLayout(self);layout.setContentsMargins(12,0,0,0);layout.setSpacing(7)
        brand=QLabel('R/S');brand.setStyleSheet('color:#DC5A57;font-size:11px;font-weight:600;');layout.addWidget(brand)
        layout.addWidget(QLabel('Remote Spotter'))
        credit=secondary(CREDIT);credit.setStyleSheet('color:#B5BBC4;font-size:10px;');layout.addWidget(credit)
        layout.addStretch()
        for text,callback,name in [('−',parent.showMinimized,'minimizeWindow'),('×',parent.close,'closeWindow')]:
            button=QPushButton(text);button.setProperty('windowButton',True);button.setObjectName(name);button.setFixedSize(38,35)
            button.setAccessibleName('Свернуть' if text=='−' else 'Закрыть приложение');button.clicked.connect(callback);layout.addWidget(button)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


class PilotWindow(ConnectionWindow):
    def __init__(self,profile,**kwargs):
        super().__init__(profile,**kwargs)
        self.setWindowTitle('Remote Spotter — пилот')
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(360,246)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        frame=QFrame();frame.setObjectName('pilotFrame');outer.addWidget(frame)
        layout=QVBoxLayout(frame);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);layout.addWidget(PilotTitle(self))
        body=QWidget();body_layout=QVBoxLayout(body);body_layout.setContentsMargins(20,18,20,20);body_layout.setSpacing(0)
        status=QHBoxLayout();status.setSpacing(9)
        self.dot=QLabel();self.dot.setFixedSize(18,18);self.dot.setStyleSheet('border-radius:9px;background-color:#B5BBC4;')
        self.title=QLabel('Вы офлайн');self.title.setStyleSheet('font-size:22px;font-weight:600;')
        status.addWidget(self.dot);status.addWidget(self.title);status.addStretch();body_layout.addLayout(status);body_layout.addSpacing(17)
        details=QFormLayout();details.setHorizontalSpacing(30);details.setVerticalSpacing(10)
        game_box=QWidget();game_layout=QVBoxLayout(game_box);game_layout.setContentsMargins(0,0,0,0);game_layout.setSpacing(1)
        self.game_label=QLabel({'iracing':'iRacing','lmu':'Le Mans Ultimate'}.get(profile.game,'iRacing / LMU'))
        game_layout.addWidget(self.game_label);self.game_caption=secondary('Ожидание запуска');self.game_caption.setStyleSheet('color:#B5BBC4;font-size:11px;');game_layout.addWidget(self.game_caption)
        self.partner=QLabel('—');self.partner.setMaximumWidth(218)
        details.addRow(secondary('Игра'),game_box);details.addRow(secondary('Споттер'),self.partner);body_layout.addLayout(details)
        body_layout.addStretch();self.connect_button=QPushButton('Подключиться');self.connect_button.setFixedHeight(37);self.connect_button.setProperty('primary',True)
        self.connect_button.clicked.connect(self.connect_session);body_layout.addWidget(self.connect_button)
        layout.addWidget(body)

    def show_state(self,state):
        self.title.setText(state['title']);self.game_caption.setText(state['game_caption'])
        self.game_label.setText({'iracing':'iRacing','lmu':'Le Mans Ultimate'}.get(state.get('game_mode'),'iRacing / LMU'))
        self.partner.setText(state['partner_status']);self.partner.setToolTip(state['partner_status'])
        color='#89AD96' if state['phase']=='online' else '#DFC36F' if state['phase']=='reconnecting' else '#B5BBC4'
        self.dot.setStyleSheet(f'border-radius:9px;background-color:{color};')
        self.connect_button.setEnabled(state['can_connect']);self.connect_button.setText(state['button'] if state['can_connect'] or state['phase']=='online' else 'Подключаемся…')
        self.connect_button.setToolTip(state['reason'])

    def viewer_session(self,event):pass


def configure_logging(role,directory):
    directory.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(directory/(role+'.log'),maxBytes=500000,backupCount=2,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[handler],force=True)


def launch(role):
    if role not in ('pilot','viewer'):raise ValueError('Unknown desktop role')
    windows_identity(role)
    if role=='viewer':
        # Import WebEngine before QApplication, including the real entrypoint.
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        from .viewer import ViewerWindow
    app=QApplication(sys.argv)
    app.setApplicationName('SpotterPilot' if role=='pilot' else 'SpotterViewer')
    app.setWindowIcon(QIcon(str(icon_path())))
    app.setQuitOnLastWindowClosed(False)
    app.setOrganizationName('RemoteSpotter');app.setApplicationVersion(VERSION)
    app.setStyleSheet(STYLE)
    directory=data_dir();directory.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(directory/(role+'.lock')));lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None,'Remote Spotter','Приложение этой роли уже запущено.');return 0
    window=None
    try:
        configure_logging(role,directory)
        from .lifecycle import protect_process_tree
        protect_process_tree()
        personalized=False
        try:profile,personalized=load_startup_profile(role,directory)
        except (ValueError,OSError,RuntimeError,KeyError,TypeError):
            QMessageBox.warning(None,'Remote Spotter','Сохранённый доступ недоступен. Укажите ключи заново на этом компьютере.');profile=None
        if not profile:
            setup=Setup(role)
            if setup.exec()!=QDialog.DialogCode.Accepted:return 0
            profile=setup.profile
        if personalized:
            if not Path(profile.ssh_key).is_file():
                key,_=QFileDialog.getOpenFileName(None,'Выберите приватный SSH-ключ для VPS',str(Path.home()/'.ssh'))
                if not key:return 0
                profile.ssh_key=key
            profile.validate()
            save_profile(profile,directory)
        window=PilotWindow(profile) if role=='pilot' else ViewerWindow(profile)
        window.closed.connect(lambda:QTimer.singleShot(0,app.quit))
        exiting=threading.Event()
        def forced_exit():
            if exiting.is_set():return
            exiting.set()
            from .lifecycle import kill_owned
            logging.warning('Shutdown exceeded 6s; stopping this instance and its owned SSH children')
            kill_owned();lock.unlock();logging.shutdown()
            # Do not terminate a QThread halfway through Python cleanup. If a
            # native read/executor is stuck, exit this process as a whole.
            os._exit(0)
        def start_watchdog():
            # Also covers a native Qt/browser teardown blocking the GUI loop.
            # Daemon timers do not hold up a normal interpreter exit.
            timer=threading.Timer(7,forced_exit);timer.daemon=True;timer.start()
        window.shutdown_started.connect(start_watchdog)
        window.shutdown_timeout.connect(forced_exit)
        window.showNormal();window.raise_();window.activateWindow()
        if role=='viewer':QTimer.singleShot(0,window.connect_session)
        return app.exec()
    finally:
        if window:
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        lock.unlock()
