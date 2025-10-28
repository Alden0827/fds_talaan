from app import app, db, User

with app.app_context():
    db.drop_all()
    db.create_all()

    # Create an admin user
    admin_user = User(
        fullname='Admin User',
        username='admin',
        email='admin@example.com',
        is_approved=True,
        is_admin=True
    )
    admin_user.set_password('password')
    db.session.add(admin_user)
    db.session.commit()
