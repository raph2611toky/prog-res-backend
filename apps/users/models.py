from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone as django_timezone
from datetime import timedelta
from dotenv import load_dotenv

from apps.users.managers import UserManager
import os

load_dotenv()

def default_created_at():
    tz = os.getenv("TIMEZONE_HOURS")
    if tz.strip().startswith("-"):
        return django_timezone.now() - timedelta(hours=int(tz.replace("-","").strip()))
    return django_timezone.now() + timedelta(hours=int(tz))

class User(AbstractBaseUser):
    SEXE_CHOICE = [
        ('M', 'Masculin'),
        ('F', 'Feminin'),
        ('I', 'Inconnu')
    ]
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    sexe = models.CharField(max_length=1, choices=SEXE_CHOICE, default='F')
    password = models.CharField(max_length=250)
    picture = models.TextField(blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    profile = models.ImageField(upload_to='users/profiles', default='users/profiles/default.png')
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_anonymous = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=django_timezone.now)
    
    USERNAME = None
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'birth_date', 'sexe']
    
    objects = UserManager()
    
    def __str__(self):
        return self.name

    class Meta:
        db_table = 'users'
        

class SmsOrangeToken(models.Model):
    id_sms_orange_token = models.AutoField(primary_key=True)
    token_access = models.CharField(max_length=255)
    token_type = models.CharField(max_length=50)
    token_validity = models.PositiveIntegerField()
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.token_access
    
    class Meta:
        db_table = 'smsorangetoken'
        
class UserOtp(models.Model):
    code_otp = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    expirer_le = models.DateTimeField()
    date_creation = models.DateTimeField(default=default_created_at)

    def __str__(self):
        return self.code_otp
    
    @property
    def is_authenticated(self):
        return self.is_active
    
    class Meta:
        db_table = "userotp"