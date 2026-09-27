"""
Seed demo accounts so you can log in immediately.

Run:  python -m scripts.seed
"""
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models import User, UserRole

# This setup script creates the local demo accounts used to test the main
# MediExplain+ roles and multilingual patient flows. It seeds administrator,
# doctor, assistant, cross-check reviewer and patient accounts, assigns the
# relevant role and language settings, skips users that already exist, hashes
# demo passwords before storage, and prints the available test logins once the
# database has been populated.

DEMO_USERS = [
    dict(email="admin@demo.com", full_name="MediExplain Admin", password="demo1234", role=UserRole.ADMIN),
    # Doctors
    dict(email="doctor@demo.com", full_name="Dr. Ihtsham",
         password="demo1234", role=UserRole.DOCTOR,
         specialty="Internal Medicine", clinic="Sharif Medical City"),
    dict(email="doctor2@demo.com", full_name="Dr. Mehwish Nawaz",
         password="demo1234", role=UserRole.DOCTOR,
         specialty="General Physician", clinic="Al-Shifa Medical Center"),
    # Delegated pre-review assistant (cannot approve or release)
    dict(email="assistant@demo.com", full_name="Clinical Assistant",
         password="demo1234", role=UserRole.ASSISTANT,
         specialty="Clinical Assistant", clinic="Sharif Medical City"),
    # Cross-check reviewer
    dict(email="reviewer@demo.com", full_name="Dr. Faisal",
         password="demo1234", role=UserRole.CROSS_CHECK_DOCTOR,
         specialty="Internal Medicine", clinic="Shalamar Hospital"),
    # Patients — one per language so you can demo all of them
    dict(email="patient.en@demo.com", full_name="John Smith",
         password="demo1234", role=UserRole.PATIENT, preferred_language="en"),
    dict(email="patient.ur@demo.com", full_name="Erum Shamshad",
         password="demo1234", role=UserRole.PATIENT, preferred_language="ur"),
    dict(email="patient.ar@demo.com", full_name="Ahmad Hassan",
         password="demo1234", role=UserRole.PATIENT, preferred_language="ar"),
    dict(email="patient.pa@demo.com", full_name="Hardeep Singh",
         password="demo1234", role=UserRole.PATIENT, preferred_language="pa_shah"),
    dict(email="patient.ps@demo.com", full_name="Khan Wali",
         password="demo1234", role=UserRole.PATIENT, preferred_language="ps"),
    dict(email="patient.sd@demo.com", full_name="Sassi Soomro",
         password="demo1234", role=UserRole.PATIENT, preferred_language="sd"),
]


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        for spec in DEMO_USERS:
            existing = await db.execute(select(User).where(User.email == spec["email"]))
            if existing.scalar_one_or_none():
                print(f"  · {spec['email']} already exists, skipping")
                continue
            user = User(
                email=spec["email"],
                full_name=spec["full_name"],
                hashed_password=hash_password(spec["password"]),
                role=spec["role"],
                preferred_language=spec.get("preferred_language", "en"),
                specialty=spec.get("specialty"),
                clinic=spec.get("clinic"),
                is_verified=True,
            )
            db.add(user)
            print(f"  ✓ Created {spec['email']} ({spec['role'].value})")
        await db.commit()
    print("\nDemo logins (all password: demo1234):")
    for s in DEMO_USERS:
        print(f"  - {s['email']:<22}  →  {s['role'].value}")


if __name__ == "__main__":
    asyncio.run(main())
