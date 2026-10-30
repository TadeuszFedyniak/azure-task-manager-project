import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "local-only-change-this-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
templates = Jinja2Templates(directory="app/templates")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    tasks: Mapped[list["Task"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    owner: Mapped[User] = relationship(back_populates="tasks")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Task Manager", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=COOKIE_SECURE,
    same_site="lax",
    max_age=60 * 60 * 8,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, int(user_id))


def page(request: Request, name: str, context: dict, status_code: int = 200):
    context.update({"request": request})
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    tasks = db.scalars(select(Task).where(Task.owner_id == user.id).order_by(Task.id.desc())).all()
    return page(request, "tasks.html", {"user": user, "tasks": tasks})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return page(request, "register.html", {"error": None})


@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip().lower()
    if len(username) < 3 or len(username) > 80:
        return page(request, "register.html", {"error": "Nazwa użytkownika musi mieć 3–80 znaków."}, 400)
    if len(password) < 12:
        return page(request, "register.html", {"error": "Hasło musi mieć co najmniej 12 znaków."}, 400)
    if db.scalar(select(User).where(User.username == username)):
        return page(request, "register.html", {"error": "Taka nazwa użytkownika już istnieje."}, 409)
    user = User(username=username, password_hash=pwd_context.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return page(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if not user or not pwd_context.verify(password, user.password_hash):
        return page(request, "login.html", {"error": "Nieprawidłowy login lub hasło."}, 401)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def owned_task(task_id: int, user: User, db: Session) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id))
    if not task:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania")
    return task


@app.post("/tasks")
def create_task(request: Request, title: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    title = title.strip()
    if not title or len(title) > 160:
        raise HTTPException(status_code=400, detail="Tytuł musi mieć 1–160 znaków")
    db.add(Task(title=title, description=description.strip()[:4000], owner_id=user.id))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/edit")
def edit_task(task_id: int, request: Request, title: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    task = owned_task(task_id, user, db)
    title = title.strip()
    if not title or len(title) > 160:
        raise HTTPException(status_code=400, detail="Tytuł musi mieć 1–160 znaków")
    task.title = title
    task.description = description.strip()[:4000]
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    task = owned_task(task_id, user, db)
    task.done = not task.done
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    task = owned_task(task_id, user, db)
    db.delete(task)
    db.commit()
    return RedirectResponse("/", status_code=303)
