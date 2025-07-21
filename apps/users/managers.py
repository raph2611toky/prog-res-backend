from django.contrib.auth.models import BaseUserManager
from django.utils import timezone
from datetime import timedelta

class UserManager(BaseUserManager):
    
    def _create_user(self, email, password, is_staff, is_superuser, **extra_fields):
        if not email:
            raise ValueError('User must have an email address')
        now = timezone.localtime(timezone.now()) + timedelta(hours=3)
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            is_staff=is_staff,
            is_superuser=is_superuser, 
            is_active=False,
            last_login=now,
            date_joined=now,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
        
    def create_user(self, name, email, password, **extra_fields):
        return self._create_user(email, password, False, False, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        return self._create_user(email, password, True, True, **extra_fields)