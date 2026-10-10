import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def delete(self, *args, **kwargs):
        from apps.tenants.signals import ensure_not_sole_owner

        ensure_not_sole_owner(self)
        return super().delete(*args, **kwargs)


class AuthToken(models.Model):
    """A bearer token a client swaps a password for once, then sends instead.

    Only the SHA-256 of the token is stored, so a database leak does not leak
    usable credentials. Tokens are 256-bit random values, so an unsalted fast
    hash is safe, and verifying one costs a single indexed lookup instead of
    a PBKDF2 run (D-18).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_tokens")
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"token for {self.user_id} (expires {self.expires_at:%Y-%m-%d %H:%M})"

    @staticmethod
    def hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def issue(cls, user):
        """Create a token for `user`; returns (instance, plaintext key)."""
        key = secrets.token_urlsafe(32)
        ttl = timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS)
        token = cls.objects.create(
            user=user, key_hash=cls.hash_key(key), expires_at=timezone.now() + ttl
        )
        return token, key
