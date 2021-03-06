from model.base import Base
from sqlalchemy import Column, Integer

class LogPosition(Base):
  """A position in a log, incremented whenever writes to particular tables occur.

  This is for syncing changes to other clients. (We don't use timestamps, since timestamps in SQL
  are not guaranteed to be unique, and not guaranteed to be written in the order that transactions
  are committed; as a result, relying on them for ordering when doing a sync can lead to entities
  being missed.)

  Models that contribute to LogPosition should have a logPosition (relationship) and logPositionId
  (foreign key to log_position_id below). Whenever they are created or updated, the associated DAO
  must overwrite the model's logPosition with a new LogPosition() which, when the object is
  committed, will increment the global log.
  """
  __tablename__ = 'log_position'
  logPositionId = Column('log_position_id', Integer, primary_key=True)
