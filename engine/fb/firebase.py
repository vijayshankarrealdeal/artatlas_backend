from firebase_admin import auth
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional



class FirebaseBearer(HTTPBearer):
    async def __call__(
        self, request: Request
    ) -> Optional[HTTPAuthorizationCredentials]:
        # First, call the parent to get the credentials
        creds = await super().__call__(request)

        if not creds:
            # This is handled by the parent, but we can be explicit
            raise HTTPException(status_code=401, detail="Bearer token not provided")

        id_token = creds.credentials

        try:
            # Verify the token using the Firebase Admin SDK
            decoded_token = auth.verify_id_token(id_token)
        except auth.ExpiredIdTokenError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except auth.InvalidIdTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
        except Exception as e:
            # Handle other potential errors during verification
            raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

        # The Firebase user's unique ID
        firebase_uid = decoded_token["uid"]
        user_record = {
                "uid": firebase_uid,
                "email": decoded_token.get("email"),
                # "name": decoded_token.get("name"), # if you have a name column
            }
    
        request.state.user = user_record
        return user_record 
    

oauth2_scheme = FirebaseBearer()
