from django.contrib.auth import password_validation
from django.contrib.auth.models import Permission
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role, User
from .roles import ensure_admin_role, ensure_user_role


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
    roles = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), many=True, required=False)
    role_details = RoleSerializer(source="roles", many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "organization", "roles", "role_details", "is_staff", "date_joined",
        ]
        read_only_fields = ["id", "is_staff", "date_joined"]


class UserSummarySerializer(serializers.ModelSerializer):
    """Lightweight representation used in share pickers / dropdowns."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "display_name"]

    def get_display_name(self, obj):
        full_name = obj.get_full_name()
        return full_name or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    """Public sign-up. New accounts receive the standard ``User`` role."""

    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "password_confirm"]

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
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


class TokenObtainPairWithUserSerializer(TokenObtainPairSerializer):
    """Adds the authenticated user's profile; accepts username or email."""

    def validate(self, attrs):
        identifier = (attrs.get(self.username_field) or "").strip()
        if identifier:
            user = User.objects.filter(username__iexact=identifier).first()
            if user is None:
                user = User.objects.filter(email__iexact=identifier).first()
            if user is not None:
                attrs[self.username_field] = user.get_username()

        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
