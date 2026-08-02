from app.database import Base, engine

from app.models.user import User
from app.models.job import Job
from app.models.resume import Resume
from app.models.application import Application
from app.models.notification import Notification
from app.models.agent_log import AgentLog

Base.metadata.create_all(bind=engine)

print("Tables created successfully")