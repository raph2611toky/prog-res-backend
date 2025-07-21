from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.conf import settings

from apps.users.models import User

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import PasswordField

from uuid import uuid4

class UserSerializer(serializers.ModelSerializer):
    profile_url = serializers.SerializerMethodField()
    birth_date = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'name', 'email','birth_date', 'profile_url', 'sexe','is_active']
    
    def get_profile_url(self, obj):
        if obj.picture is not None:
            return obj.picture
        return f'{settings.BASE_URL}{obj.profile.url}' if obj.profile else None
    
    def get_birth_date(self,obj):
        if obj.birth_date is not None:
            return obj.birth_date.strftime('%d-%m-%Y')
        return None
    
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = PasswordField()
    
    def validate(self, attrs):
        users = authenticate(**attrs)
        if not users:
            raise AuthenticationFailed()
        users_logged = User.objects.get(id=users.id)
        users_logged.is_active = True
        update_last_login(None, users_logged)
        users_logged.save()
        data = {}
        refresh = self.get_token(users_logged)
        data['access'] = str(refresh.access_token)
        data['name'] = users_logged.name
        data['sexe'] = users_logged.sexe
        return data
    
    def get_token(self, users):
        token = RefreshToken.for_user(users)
        return token

class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['name', 'sexe', 'birth_date', 'profile']

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
    
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['email', 'password', 'name', 'sexe', 'birth_date']

    def validate(self, attrs):
        self.create(attrs)
        return attrs
    
    def create(self, validated_data):
        is_staff=False
        users = User.objects.create(
            name=validated_data['name'].capitalize(),
            email=validated_data['email'],
            sexe=validated_data.get('sexe','I')[0].upper(),
            birth_date=validated_data['birth_date'],
            is_superuser=False,
            is_staff=is_staff
        )
        users.set_password(validated_data['password'])
        users.is_active = False
        users.save()
        user_created = User.objects.get(id=users.id)
        print(validated_data)
        data = {
            'email': user_created.email,
            'user':users
        }
        return data