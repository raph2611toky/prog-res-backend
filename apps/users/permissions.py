from rest_framework.permissions import BasePermission
from helpers.helper import get_token_from_request, get_support
from django.contrib.auth.models import AnonymousUser

class IsAuthenticatedSupport(BasePermission):
    def has_permission(self, request, view):
        token = get_token_from_request(request)
        if not token:
            return False

        support = get_support(token)
        if support is None or isinstance(support, AnonymousUser):
            return False
        
        if not support.est_actif:
            return False
        
        request.support = support
        return True