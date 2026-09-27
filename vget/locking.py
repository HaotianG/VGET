"""Reentrant process + thread lock for local CLI and GUI transactions."""
import os
import threading
import time

try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

_LOCKS = {}
_GUARD = threading.Lock()

def workspace_lock(path):
    key = str(path.resolve())
    with _GUARD:
        return _LOCKS.setdefault(key, WorkspaceLock(path))

class WorkspaceLock:
    def __init__(self,path):
        self.path=path
        self.thread_lock=threading.RLock()
        self.depth=0
        self.file=None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            if self.depth==0:
                self.file=self.path.open('a+b')
                if os.fstat(self.file.fileno()).st_size==0:
                    self.file.write(b'0');self.file.flush()
                deadline=time.monotonic()+15
                while True:
                    try:
                        self.file.seek(0)
                        if fcntl:fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                        else:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
                        break
                    except (BlockingIOError,OSError):
                        if time.monotonic()>=deadline:raise TimeoutError('Workspace is busy; retry after the active operation finishes.')
                        time.sleep(.025)
            self.depth+=1
            return self
        except BaseException:
            if self.file:self.file.close();self.file=None
            self.thread_lock.release()
            raise

    def __exit__(self,*exc):
        self.depth-=1
        if self.depth==0:
            try:
                self.file.seek(0)
                if fcntl:fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
                else:msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            finally:self.file.close();self.file=None
        self.thread_lock.release()
