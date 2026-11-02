from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
import getpass
import os
import subprocess
import sys


TASK_NAME = "LaobingMarketIntelligence-DailyMonitor"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_MAX_AGE_SECONDS = 4 * 60 * 60


def validate_run_time(run_time):
    if (
        not isinstance(run_time, str)
        or len(run_time) != 5
        or run_time[2] != ":"
        or not run_time[:2].isdigit()
        or not run_time[3:].isdigit()
    ):
        raise ValueError("执行时间需要使用 HH:MM 格式")
    hour = int(run_time[:2])
    minute = int(run_time[3:])
    if hour > 23 or minute > 59:
        raise ValueError("执行时间超出有效范围")
    return hour, minute


def scheduled_action():
    if bool(getattr(sys, "frozen", False)):
        return Path(sys.executable), "--run-monitor", Path(sys.executable).parent
    return (
        Path(sys.executable),
        f'"{PROJECT_ROOT / "monitor_runner.py"}"',
        PROJECT_ROOT,
    )


def build_windows_task_xml(run_time, *, now=None):
    hour, minute = validate_run_time(run_time)
    current = now or datetime.now().astimezone()
    boundary = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if boundary <= current:
        boundary += timedelta(days=1)
    command, arguments, working_directory = scheduled_action()
    domain = str(os.environ.get("USERDOMAIN") or "").strip()
    username = getpass.getuser()
    user_id = f"{domain}\\{username}" if domain else username
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>淘宝选品竞品情报操作台每日监控</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{boundary.isoformat(timespec="seconds")}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user_id)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(command))}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(working_directory))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''


def _run_schtasks(arguments):
    if os.name != "nt":
        raise RuntimeError("定时监控目前仅支持 Windows")
    completed = subprocess.run(
        ["schtasks.exe", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    return completed


def install_windows_schedule(application_data_directory, run_time):
    schedule_directory = Path(application_data_directory) / "scheduler"
    schedule_directory.mkdir(parents=True, exist_ok=True)
    xml_path = schedule_directory / "daily-monitor.xml"
    xml_path.write_text(build_windows_task_xml(run_time), encoding="utf-16")
    completed = _run_schtasks(["/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"])
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "未知错误").strip()
        raise RuntimeError(f"Windows 定时任务创建失败：{message}")
    return {"task_name": TASK_NAME, "run_time": run_time, "installed": True}


def remove_windows_schedule():
    completed = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        normalized = message.casefold()
        if "cannot find" not in normalized and "找不到" not in message:
            raise RuntimeError(f"Windows 定时任务移除失败：{message or '未知错误'}")
    return {"task_name": TASK_NAME, "installed": False}


class MonitorRunLock:
    def __init__(self, application_data_directory):
        self.path = Path(application_data_directory) / "scheduler" / "monitor.lock"
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age_seconds = datetime.now().timestamp() - self.path.stat().st_mtime
            if age_seconds > LOCK_MAX_AGE_SECONDS:
                self.path.unlink(missing_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return self
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(f"pid={os.getpid()}\nstarted_at={datetime.now().astimezone().isoformat()}\n")
        self.acquired = True
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        if self.acquired:
            self.path.unlink(missing_ok=True)

