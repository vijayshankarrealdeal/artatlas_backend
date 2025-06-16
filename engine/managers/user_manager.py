from pymongo.database import Database
from engine.models.user_model import UserApp

class UserManager:

    def check_user(db: Database, user_id: str, email: str) -> UserApp:
        """
        Checks if a user exists in the database by user_id.
        If not, creates a new user with the provided email.
        """
        user_collection = db["users"]
        user_data = user_collection.find_one({"_id": user_id})

        if not user_data:
            new_user = UserApp(_id=user_id, email=email)
            user_collection.insert_one(new_user.model_dump(by_alias=True))
            user = new_user
        else:
            user = UserApp(**user_data)
        return user