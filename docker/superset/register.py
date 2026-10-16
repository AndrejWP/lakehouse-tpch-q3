"""Idempotent admin/connection registration, executed inside Superset."""
import os
from uuid import UUID
from superset.app import create_app
app = create_app()
with app.app_context():
    from superset import db, security_manager
    from superset.models.core import Database
    user = security_manager.find_user(username=os.environ['SUPERSET_ADMIN_USER'])
    if user is None:
        user = security_manager.add_user(
            username=os.environ['SUPERSET_ADMIN_USER'], first_name='Local',
            last_name='Admin', email='admin@localhost.invalid',
            role=security_manager.find_role('Admin'),
            password=os.environ['SUPERSET_ADMIN_PASSWORD'])
        if not user:
            raise RuntimeError('Cannot create Superset admin')
    connection = db.session.query(Database).filter_by(database_name='Lakehouse Trino').one_or_none()
    if connection is None:
        connection = Database(database_name='Lakehouse Trino', uuid=UUID('b1e6f7e2-d98a-4098-9c18-eb194890e1df'))
        db.session.add(connection)
    connection.sqlalchemy_uri = 'trino://superset@trino:8080/lakehouse/bronze'
    connection.expose_in_sqllab = True
    connection.allow_dml = False
    db.session.commit()
