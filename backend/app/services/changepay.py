from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass
class ChangepayUser:
    user_id: str
    phone: str
    email: str | None
    display_name: str
    customer_token: str


class ChangepayError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ChangepayClient:
    def __init__(self):
        self.base_url = settings.changepay_base_url.rstrip("/")
        self.tpid = settings.changepay_tpid

    async def request_otp(self, phone: str) -> dict:
        """
        Returns the full response — in staging this includes the OTP token.
        In production the OTP is delivered by SMS and the token field is absent.
        """
        url = f"{self.base_url}/api/v1/auth/token/"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={"third_party_id": self.tpid, "phone": phone})
        if resp.status_code not in (200, 201):
            raise ChangepayError("Failed to send OTP. Check the phone number and try again.", resp.status_code)
        return resp.json()

    async def login_with_otp(self, phone: str, otp: str) -> ChangepayUser:
        user_token = await self._get_user_token({"phone": phone, "token": otp, "third_party_id": self.tpid})
        return await self._get_customer_profile(user_token)

    async def login_with_password(self, phone: str, password: str) -> ChangepayUser:
        user_token = await self._get_user_token({"phone": phone, "password": password, "third_party_id": self.tpid})
        return await self._get_customer_profile(user_token)

    async def _get_user_token(self, payload: dict) -> str:
        url = f"{self.base_url}/api/v1/auth/token/"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
        if resp.status_code not in (200, 201):
            raise ChangepayError("Invalid credentials. Please try again.", 401)
        data = resp.json()
        token = data.get("token")
        if not token:
            raise ChangepayError("Unexpected response from authentication service.", 502)
        return token

    async def _get_customer_profile(self, user_token: str) -> ChangepayUser:
        url = f"{self.base_url}/api/v1/auth/profiles"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"Authorization": f"JWT {user_token}"})
        if resp.status_code != 200:
            raise ChangepayError("Failed to retrieve profile.", 502)

        data = resp.json()
        customer = data.get("CUSTOMER")
        if not customer:
            raise ChangepayError(
                "StudyBuddy is only available to ChangePay Customers. "
                "Please ensure you are registered as a Customer on ChangePay.",
                403,
            )

        profile_data = customer.get("data", {})
        if profile_data.get("is_suspended"):
            raise ChangepayError(
                "Your ChangePay account is suspended. Please contact ChangePay support.",
                403,
            )

        user_profile = profile_data.get("user_profile", {})
        return ChangepayUser(
            user_id=user_profile["user_id"],
            phone=user_profile["phone"],
            email=user_profile.get("email"),
            display_name=profile_data.get("profile_name", user_profile["phone"]),
            customer_token=customer["token"],
        )


changepay_client = ChangepayClient()
