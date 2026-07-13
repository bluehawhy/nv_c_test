import sys
import time
import re
import os

from PyQt6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QLineEdit, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton)
from PyQt6.QtCore import Qt, QTimer, QObject, QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import selenium.webdriver.chrome.webdriver

# --- 1. 백그라운드 초기화 스레드 ---
class InitWorker(QThread):
    finished = pyqtSignal()
    status_msg = pyqtSignal(str)

    def __init__(self, bot ,restart=False):
        super().__init__()
        self.bot = bot
        self.restart = restart

    def run(self):
        try:
            if self.restart:
                self.status_msg.emit(" (재시작 중...)")
                self.bot.restart_driver()
            else:
                self.status_msg.emit(" (연결 중...)")
                self.bot.setup_driver()

            self.status_msg.emit(" (연결됨)")
            self.finished.emit()

        except Exception as e:
            self.status_msg.emit(" (연결 실패)")
            print(f"드라이버 작업 실패: {e}")

# --- 2. Selenium 엔진 클래스 (tlk.io 맞춤 수정) ---
class JitsiBot(QObject):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.driver = None
        self.last_msg_count = 0
        self.nickname = self.load_nickname()

    def load_nickname(self):
        try:          
            # 1. 현재 실행 중인 파일의 이름만 추출 (예: nv_nkm_tool_v2_홍길동.exe)
            current_filename = os.path.basename(sys.argv[0])
            match = re.match(r".*_([^.]+)\.(?:exe|py)$", current_filename, re.IGNORECASE)
            
            if match:
                return match.group(1)
                
            return "MemoBot"
            
        except Exception:
            return "MemoBot"

    def setup_driver(self):
        options = Options()
        options.add_argument("--mute-audio")
        try:
            current_filename = os.path.basename(sys.argv[0])
            # unheadless가 파일명에 '없을 때만' headless 추가
            if "unheadless" not in current_filename.lower():
                options.add_argument("--headless")
        except Exception:
            # 에러 발생 시(파일명 읽기 실패 등) 안전하게 기본값인 headless 적용
            options.add_argument("--headless")
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.driver.get(self.url)
        time.sleep(3) # 페이지 로딩 대기
        
        try:
            # tlk.io의 'Wanna join?' 닉네임 설정 창 설정 체크
            nickname_input = self.driver.find_elements(By.CSS_SELECTOR, "#participant_nickname")
            
            if nickname_input and nickname_input[0].is_displayed():
                nickname_input[0].send_keys(self.nickname)
                nickname_input[0].send_keys(Keys.ENTER)
                time.sleep(2) # 로그인 처리 대기
        except Exception as e:
            print(f"로그인 처리 중 예외 발생: {e}")

        # [수정] tlk.io의 실제 메시지 노드인 '.post' 기준으로 카운트 초기화
        try:
            current_msgs = self.driver.find_elements(By.CSS_SELECTOR, "#chat .post")
            self.last_msg_count = len(current_msgs)
        except:
            self.last_msg_count = 0

    def restart_driver(self):
        """새로고침이 아닌 드라이버 자체를 완전히 재부팅"""
        print("🔄 크롬 드라이버 재시작 프로세스 가동...")
        # --- [추가] 기존에 남아있는 드라이버 세션을 안전하게 종료 ---
        if hasattr(self, 'driver') and self.driver:
            try:
                print("🛑 기존 크롬 드라이버 인스턴스 종료 중...")
                self.driver.quit()
            except Exception as e:
                print(f"⚠️ 기존 드라이버 종료 중 예외 발생 (이미 죽었을 수 있음): {e}")
            finally:
                self.driver = None # 참조 해제
        # 새 드라이버 시작
        self.setup_driver()

    def refresh_chat(self):
        if not self.driver:
            print("⚠️ 드라이버가 준비되지 않아 새로고침할 수 없습니다.")
            return False
            
        try:
            print("🔄 웹드라이버 새로고침 시작...")
            self.driver.refresh()
            time.sleep(3) # 페이지 로딩 대기
            
            # 1. 닉네임 입력창이 뜨면 입력하고, 없으면(지정되어 있으면) 그냥 넘어감
            try:
                nickname_input = self.driver.find_elements(By.CSS_SELECTOR, "#participant_nickname")
                if nickname_input and nickname_input[0].is_displayed():
                    nickname_input[0].send_keys(self.nickname)
                    nickname_input[0].send_keys(Keys.ENTER)
                    time.sleep(2) # 로그인 처리 대기
                    print(f"✅ 닉네임('{self.nickname}') 재입력 완료.")
                else:
                    print("ℹ️ 닉네임이 이미 지정되어 있거나 입력창이 뜨지 않았습니다.")
            except Exception as e:
                print(f"닉네임 재확인 중 예외 발생: {e}")

            # 2. 메시지 추적용 데이터 초기화 (세트 방식 기준)
            if hasattr(self, 'seen_msg_ids'):
                self.seen_msg_ids.clear() # 기존에 저장된 ID들 리셋
                try:
                    current_msgs = self.driver.find_elements(By.CSS_SELECTOR, "#chat dl.post dd.post-message")
                    for elem in current_msgs:
                        self.seen_msg_ids.add(elem.id)
                    print(f"🔄 새로고침 후 기존 메시지 {len(current_msgs)}개 제외 완료.")
                except:
                    pass
            # (만약 예전 카운트 방식을 쓰고 계신다면 아래 주석을 해제하고 위 세트 코드를 지우세요)
            # else:
            #     try:
            #         current_msgs = self.driver.find_elements(By.CSS_SELECTOR, "#chat dl.post dd.post-message")
            #         self.last_msg_count = len(current_msgs)
            #     except:
            #         self.last_msg_count = 0

            return True
        except Exception as e:
            print(f"❌ 새로고침 중 오류 발생: {e}")
            return False



    def get_new_messages(self):
        if not self.driver: return []
        try:
            # 1. tlk.io의 실제 메시지 알맹이 단위(dd.post-message)를 전부 긁어옵니다.
            all_messages = self.driver.find_elements(By.CSS_SELECTOR, "#chat dl.post dd.post-message")
            #print(f'get new - {all_messages}')
            current_count = len(all_messages)
            
            # 2. 첫 실행 시점(초기 로딩) 방어 코드
            if self.last_msg_count == 0 and current_count > 0:
                self.last_msg_count = current_count
                return []

            # 3. 새로운 메시지(dd)가 추가되었을 때만 파싱 진행
            if all_messages and current_count > self.last_msg_count:
                new_elements = all_messages[self.last_msg_count:]
                self.last_msg_count = current_count
                
                new_msgs = []
                for elem in new_elements:
                    try:
                        # [핵심] 텍스트 추출 (말풍선 안의 순수 텍스트만 가져오기 위해 시간 레이블 제외)
                        # tlk.io 구조상 dd 태그의 첫 번째 텍스트 노드가 순수 메시지 본문입니다.
                        full_text = elem.text.strip()
                        time_tag_elem = elem.find_elements(By.CSS_SELECTOR, ".post-time")
                        if time_tag_elem:
                            time_text = time_tag_elem[0].text.strip()
                            text = full_text.replace(time_text, "").strip()
                        else:
                            text = full_text

                        # [핵심] 현재 dd의 부모 <dl> 엘리먼트로 거슬러 올라가 내부의 .post-name 을 추적
                        # 이 방식을 쓰면 한 유저가 여러 줄을 보내도 이름 유실 없이 완벽히 매치됩니다.
                        parent_dl = elem.find_element(By.XPATH, "./parent::dl")
                        sender_elem = parent_dl.find_elements(By.CSS_SELECTOR, ".post-name")
                        
                        if sender_elem and sender_elem[0].text.strip():
                            sender = sender_elem[0].text.strip()
                        else:
                            # 만약의 상황을 대비해 부모 태그의 data 속성 백업 추적
                            user_nickname = parent_dl.get_attribute("data-user-nickname")
                            sender = user_nickname if user_nickname else "상대방"

                        if text:
                            new_msgs.append({
                                "sender": sender,
                                "text": text
                            })
                    except Exception as e:
                        continue
                return new_msgs
                
            elif current_count < self.last_msg_count:
                self.last_msg_count = current_count
                
        except Exception as e:
            print(f"메시지 수집 중 오류 발생: {e}")
        return []

    
    def send_message(self, text):
        if not self.driver: 
            print("⚠️ 드라이버가 아직 준비되지 않았습니다.")
            return
        try:
            # tlk.io 입력창 선택 (#message_body)
            chat_input = self.driver.find_element(By.CSS_SELECTOR, "#message_body")
            chat_input.send_keys(text)
            chat_input.send_keys(Keys.ENTER)
        except Exception as e:
            print(f"❌ 메시지 전송 실패: {e}")

    def quit(self):
        if self.driver:
            try: self.driver.quit()
            except: pass

# --- 3. UI 클래스 ---
class ChatUI(QMainWindow):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.ver = "Tlk.io Remote v4.2_"
        self.commands = ["/re", "/clear", "/help", "/h",'/restart']
        self.init_ui()
        
        # 백그라운드 연결 시작
        self.worker = InitWorker(self.bot)
        self.worker.status_msg.connect(self.update_status_label)
        self.worker.finished.connect(self.on_init_finished)
        self.worker.start()

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                            Qt.WindowType.WindowStaysOnTopHint | 
                            Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(350, 400)
        
        self.container = QWidget()
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(243, 243, 243, 0.5); 
                border-radius: 20px;
                border: none;
            }
        """)
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 15, 20, 15)
        
        # 헤더 레이아웃
        header_layout = QHBoxLayout()
        self.status = QLabel(f"💬 {self.ver}")
        self.status.setStyleSheet("color: #333; font-weight: bold; font-size: 10px; background: transparent;")
        
        btn_style = """
            QPushButton {
                color: #555; font-weight: bold; font-size: 12px;
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(233, 233, 233, 0.15); border-radius: 5px; margin-left: 5px;
            }
            QPushButton:hover { color: #ff5f56; background-color: rgba(255, 255, 255, 0.3); }
        """

        self.min_btn = QPushButton("—")
        self.min_btn.setFixedSize(20, 20)
        self.min_btn.setStyleSheet(btn_style)
        self.min_btn.clicked.connect(self.showMinimized)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(self.force_close)
        
        header_layout.addWidget(self.status)
        header_layout.addStretch()
        header_layout.addWidget(self.min_btn)
        header_layout.addWidget(self.close_btn)
        main_layout.addLayout(header_layout)

        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.setStyleSheet("border: none; background: transparent; color: #2c3e50; font-size: 10px; padding: 0px;")
        main_layout.addWidget(self.display)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("연결 대기 중...")
        self.input.setEnabled(False) 
        self.input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.2); 
                color: #333; padding: 8px; border-radius: 10px; font-size: 10px; border: none;
            }
        """)
        self.input.returnPressed.connect(self.handle_send)
        main_layout.addWidget(self.input)
        
        from PyQt6.QtGui import QAction, QKeySequence
        
        # 1. 백틱(`) 단축키
        self.backtick_action = QAction(self)
        self.backtick_action.setShortcut(QKeySequence("`"))
        self.backtick_action.triggered.connect(self.showMinimized)
        self.addAction(self.backtick_action)

        # 2. ESC 단축키
        self.esc_action = QAction(self)
        self.esc_action.setShortcut(QKeySequence("Esc"))
        self.esc_action.triggered.connect(self.showMinimized)
        self.addAction(self.esc_action)
        self.setCentralWidget(self.container)

    def update_status_label(self, suffix):
        self.status.setText(f"💬 {self.ver} {suffix}")

    def on_init_finished(self):
        self.input.setEnabled(True)
        self.input.setPlaceholderText("메시지 입력...")
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chat)
        self.timer.start(1000)

    def update_chat(self):
        new_msgs = self.bot.get_new_messages()
        #print(f'update_chat - {new_msgs}')
        for m in new_msgs:
            chat_html = f"<div style='margin-bottom: 2px; font-size: 10px;'><b style='color: #1a1a1a;'>{m['sender']} :</b> <span style='color: #444444;'>{m['text']}</span></div>"
            self.display.append(chat_html)
        if new_msgs:
            self.display.verticalScrollBar().setValue(self.display.verticalScrollBar().maximum())
            # --- [추가] 창이 포커스를 잃었거나 최소화된 경우 작업표시줄 깜빡임 ---
            if not self.isActiveWindow() or self.isMinimized():
                # msec=0으로 주면 사용자가 창을 클릭할 때까지 계속 깜빡입니다.
                QApplication.alert(self, msecs=0)

    def handle_send(self):
        text = self.input.text().strip()
        if text:
            # 1. 슬래시(/)로 시작하는 명령어 처리 구역
            if text.startswith("/"):
                cmd_parts = text.split()
                base_cmd = cmd_parts[0] if cmd_parts else ""

                if base_cmd in self.commands:
                    # --- [여기서부터 명령어별 실제 기능 처리] ---
                    if base_cmd == "/clear":
                        self.display.clear()  # 대화창 안의 HTML 텍스트를 모두 지웁니다.

                    elif base_cmd == "/re":
                        # 사용자에게 작업 시작을 알림
                        self.display.append("<div style='color: #3498db; font-size: 10px;'><b>[시스템]</b> 채널을 새로고침 중입니다. 잠시만 기다려주세요...</div>")
                        self.display.verticalScrollBar().setValue(self.display.verticalScrollBar().maximum())
                        QApplication.processEvents() # UI가 굳지 않고 글자가 바로 뜨도록 강제 새로고침
                        
                        # 봇의 새로고침 함수 호출
                        success = self.bot.refresh_chat()
                        self.display.append("<div style='color: #3498db; font-size: 10px;'><b>[시스템]</b> 새로고침 완료 했습니다.</div>")

                    # --- [추가된 /restart 명령어 구간] ---
                    elif base_cmd == "/restart":
                        self.input.clear()
                        self.input.setPlaceholderText("드라이버 재부팅 중...")
                        self.input.setEnabled(False)
                        self.display.append("<div style='color: #e74c3c; font-size: 10px;'><b>[시스템]</b> 크롬 드라이버를 완전히 재시작합니다. 잠시만 기다려주세요...</div>")
                        self.display.verticalScrollBar().setValue(self.display.verticalScrollBar().maximum())
                        QApplication.processEvents()

                        # 1. 타이머 중지 (재시작 중 셀레니움 명령 꼬임 방지)
                        if hasattr(self, 'timer'):
                            self.timer.stop()

                        # 2. 기존 백그라운드 스레드가 돌고 있다면 안전하게 종료 대기
                        if hasattr(self, 'worker') and self.worker.isRunning():
                            self.worker.quit()
                            self.worker.wait()

                        # 3. InitWorker 스레드를 다시 활용하여 백그라운드에서 restart_driver 가동
                        self.worker = InitWorker(self.bot ,restart=True)
                        self.worker.status_msg.connect(self.update_status_label)
                        self.worker.finished.connect(self.on_init_finished)
                        self.worker.start()
                        return  # 스레드가 도는 동안 중복 입력을 막기 위해 즉시 리턴 처리합니다.

                    elif base_cmd in ["/help", "/h"]:
                        # 각 명령어의 기능 설명을 예쁘게 포맷팅하여 출력합니다. (/restart 가이드 추가)
                        help_msg = (
                            "<div style='color: #e67e22; font-size: 10px; line-height: 140%; margin-bottom: 2px;'>"
                            "<b>💡 [명령어 도움말 가이드]</b><br>"
                            "--------------------------------------------------<br>"
                            "<b>• /clear</b> : 내장 대화창의 모든 텍스트 내역을 깨끗하게 비웁니다.<br>"
                            "<b>• /re</b> : 브라우저를 새로고침하고 닉네임을 체크하여 연결을 재설정합니다.<br>"
                            "<b>• /restart</b> : 크롬 드라이버 프로세스를 완전히 재시작합니다. (잠수 해제용)<br>"
                            "<b>• /help, /h</b> : 명령어 도움말 가이드를 출력합니다.<br>"
                            "--------------------------------------------------"
                            "</div>"
                        )
                        self.display.append(help_msg)

                    # 새 글이 추가되었을 수 있으니 스크롤을 맨 아래로 이동
                    self.display.verticalScrollBar().setValue(self.display.verticalScrollBar().maximum())
                else:
                    # 잘못된 명령어를 입력했을 때의 안내 문구
                    cmd_list_str = ", ".join(self.commands)
                    err_msg = (
                        f"<div style='color: #ff5f56; font-size: 10px; margin-bottom: 2px;'>"
                        f"<b>[시스템]</b> 해당 명령어({base_cmd})는 없습니다.<br>"
                        f"<b>[명령어 리스트]</b> {cmd_list_str}"
                        f"</div>"
                    )
                    self.display.append(err_msg)
                    self.display.verticalScrollBar().setValue(self.display.verticalScrollBar().maximum())

                self.input.clear()
                return

            # 2. 일반 메시지인 경우 기존처럼 전송
            self.bot.send_message(text)
            self.input.clear()


    # 최소화되기 전의 창 상태를 기억하기 위한 변수 (클래스 변수나 __init__에 두셔도 됩니다)
    _was_minimized = False

    def changeEvent(self, event):
        # 창의 상태가 변경되었을 때 (최소화, 최대화 등)
        if event.type() == event.Type.WindowStateChange:
            # 현재 최소화된 상태라면
            if self.isMinimized():
                self._was_minimized = True
            else:
                # 최소화 상태에서 풀려났을 때 (작업표시줄 아이콘을 다시 눌렀을 때)
                if self._was_minimized:
                    self._was_minimized = False
                    # 창을 화면 맨 앞으로 가져오고 활성화시킵니다.
                    self.showNormal()
                    self.activateWindow()
                    self.raise_()
        super().changeEvent(event)

    def mousePressEvent(self, event):
        # 기존 마우스 드래그 코드 이동 시 작동 방해를 막기 위해 유지
        if event.button() == Qt.MouseButton.LeftButton: 
            self.old_pos = event.globalPosition().toPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.old_pos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event):
        if hasattr(self, 'old_pos'):
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def force_close(self):
        self.close()

    def closeEvent(self, event):
        self.hide()
        QApplication.processEvents()
        if self.bot: self.bot.quit()
        event.accept()
        sys.exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 목표 URL을 tlk.io 주소로 변경
    target_url = "https://tlk.io/ElderlyThoughtsCopyUpwards"
    jitsi_bot = JitsiBot(target_url)
    main_window = ChatUI(jitsi_bot)
    main_window.show()
    sys.exit(app.exec())