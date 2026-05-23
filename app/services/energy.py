"""Energy Service.

Helps schedule tasks based on the user's biological clock (energy levels).
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserORM


class EnergyService:
    """Provides insights into user's energy levels throughout the day."""

    # Defaults: Morning person profile (higher energy in morning, dip after lunch, low evening)
    # Energy levels: 1 = lowest, 5 = highest
    DEFAULT_PROFILE = {
        "0": 1, "1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 2, "7": 3,
        "8": 4, "9": 5, "10": 5, "11": 4, "12": 3, "13": 2, "14": 2, "15": 3,
        "16": 4, "17": 3, "18": 2, "19": 2, "20": 2, "21": 1, "22": 1, "23": 1
    }

    async def get_energy_profile(self, session: AsyncSession, user_id: int) -> dict:
        """Get the user's energy profile, mapping hour (0-23) to energy level (1-5)."""
        user = await session.get(UserORM, user_id)
        if user and user.energy_profile:
            # fill missing hours
            profile = user.energy_profile.copy()
            for h in range(24):
                if str(h) not in profile:
                    profile[str(h)] = self.DEFAULT_PROFILE[str(h)]
            return profile
            
        return self.DEFAULT_PROFILE.copy()

    def get_energy_at(self, hour: int, profile: dict) -> int:
        """Get energy level at a specific hour."""
        return profile.get(str(hour), self.DEFAULT_PROFILE.get(str(hour), 1))

    def suggest_task_placement(self, task_priority: int, profile: dict) -> list[int]:
        """Suggest optimal hours for a task based on its priority.
        
        High priority tasks (4,5) should go to high energy hours (4,5).
        Low priority tasks (1,2) can go anywhere, but preferably lower energy hours.
        """
        # Sort hours by energy level
        hours_by_energy = sorted(
            range(24),
            key=lambda h: self.get_energy_at(h, profile),
            reverse=True
        )
        
        if task_priority >= 4:
            # Return top 1/3 high energy hours
            return hours_by_energy[:8]
        elif task_priority <= 2:
            # Return bottom 1/2 energy hours (but > 1 to avoid sleep time)
            # Actually just low energy hours during the day (level 2, 3)
            moderate_hours = [h for h in range(24) if self.get_energy_at(h, profile) in (2, 3)]
            return moderate_hours if moderate_hours else hours_by_energy[-8:]
        else:
            # Medium priority (3)
            medium_hours = [h for h in range(24) if self.get_energy_at(h, profile) in (3, 4)]
            return medium_hours if medium_hours else hours_by_energy[8:16]
