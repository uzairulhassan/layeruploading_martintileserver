from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import Permission
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .avatars import sanitize_avatar_upload
from .models import Role, User
from .roles import ensure_admin_role, ensure_user_role

IDENTITY_CONFLICT_MESSAGE = "Unable to use the provided account details."


class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "app_label"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(), many=True, required=False
    )
    permission_details = PermissionSerializer(source="permissions", many=True, read_only=True)
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = [
            "id", "name", "description", "permissions", "permission_details",
            "user_count", "created_at", "updated_at",
        ]


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    role_details = RoleSerializer(source="roles", many=True, read_only=True)
    avatar_url = serializers.CharField(read_only=True, allow_null=True)
    account_type = serializers.CharField(read_only=True)
    can_change_username = serializers.BooleanField(read_only=True)
    can_change_email = serializers.BooleanField(read_only=True)
    next_username_change_at = serializers.DateTimeField(read_only=True, allow_null=True)
    next_email_change_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "organization", "roles", "role_details", "is_staff", "date_joined",
            "avatar_url", "account_type",
            "can_change_username", "can_change_email",
            "next_username_change_at", "next_email_change_at",
        ]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Self-service profile updates for username / email (30-day cooldown each)."""

    class Meta:
        model = User
        fields = ["username", "email"]

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        UnicodeUsernameValidator()(username)
        user = self.instance
        if user and username.lower() == user.username.lower():
            return user.username
        if User.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(IDENTITY_CONFLICT_MESSAGE)
        if user and not user.can_change_username:
            raise serializers.ValidationError(
                "Username can only be changed once every 30 days."
            )
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        user = self.instance
        if user and email == user.email.lower():
            return user.email
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(IDENTITY_CONFLICT_MESSAGE)
        if user and not user.can_change_email:
            raise serializers.ValidationError(
                "Email can only be changed once every 30 days."
            )
        return email

    def update(self, instance, validated_data):
        now = timezone.now()
        if "username" in validated_data and validated_data["username"] != instance.username:
            instance.username = validated_data["username"]
            instance.username_changed_at = now
        if "email" in validated_data and validated_data["email"].lower() != instance.email.lower():
            instance.email = validated_data["email"]
            instance.email_changed_at = now
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        password_validation.validate_password(
            attrs["new_password"],
            user=self.context["request"].user,
        )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.ImageField()

    def validate_avatar(self, value):
        return sanitize_avatar_upload(value)


class UserSummarySerializer(serializers.ModelSerializer):
    """Share-picker payload — no email (directory privacy)."""

    display_name = serializers.SerializerMethodField()
    avatar_url = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "avatar_url"]

    def get_display_name(self, obj):
        full_name = obj.get_full_name()
        return full_name or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    """Public sign-up payload. Gated by ``ALLOW_PUBLIC_SIGNUP`` on the view."""

    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "password_confirm"]

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        UnicodeUsernameValidator()(username)
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError(IDENTITY_CONFLICT_MESSAGE)
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(IDENTITY_CONFLICT_MESSAGE)
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        password_validation.validate_password(attrs["password"])
        return attrs

    def prepare_user(self, user):
        """Hook for subclasses to set flags before save."""

    def assign_role(self, user):
        user.roles.add(ensure_user_role())

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        self.prepare_user(user)
        user.save()
        self.assign_role(user)
        return user


class OnetimeRegisterSerializer(RegisterSerializer):
    """Bootstrap registration for the first account — assigned the ``Admin`` role."""

    def prepare_user(self, user):
        user.is_staff = True
        user.is_superuser = True

    def assign_role(self, user):
        user.roles.add(ensure_admin_role())


class UsernameAvailabilitySerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        UnicodeUsernameValidator()(username)
        return username


def _resolve_login_identifier(identifier: str) -> str:
    """Map username-or-email input to the canonical username for auth."""
    identifier = (identifier or "").strip()
    if not identifier:
        return identifier
    user = User.objects.filter(username__iexact=identifier).first()
    if user is None:
        user = User.objects.filter(email__iexact=identifier).first()
    return user.get_username() if user is not None else identifier


class SessionLoginSerializer(serializers.Serializer):
    """Browser sign-in: validates credentials without issuing JWTs."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = _resolve_login_identifier(attrs.get("username"))
        password = attrs.get("password")
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed("Invalid username/email or password.")
        self.user = user
        return attrs


class TokenObtainPairWithUserSerializer(TokenObtainPairSerializer):
    """JWT pair for API clients; accepts username or email."""

    def validate(self, attrs):
        identifier = (attrs.get(self.username_field) or "").strip()
        if identifier:
            attrs[self.username_field] = _resolve_login_identifier(identifier)

        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data

