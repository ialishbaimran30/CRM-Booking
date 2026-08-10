from rest_framework import serializers
from .models import TeamRoleAssignment
from .permissions import get_user_role
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
User = get_user_model()




class GoogleSignInSerializer(serializers.Serializer):
    id_token = serializers.CharField(write_only=True, trim_whitespace=True, max_length=10000)

    def validate_id_token(self, value):
        if not value:
            raise serializers.ValidationError("Google ID token is required.")
        return value


class EmailOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(
        regex=r"^\d{6}$",
        error_messages={"invalid": "Enter the 6-digit code."},
    )


class AuthenticatedUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    profile_picture_url = serializers.URLField(read_only=True, allow_blank=True)
    role = serializers.SerializerMethodField()

    def get_role(self, obj):
        return get_user_role(obj)


class TeamRoleSerializer(serializers.ModelSerializer):
    assigned_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='assigned_user', allow_null=True, required=False
    )
    assigned_user_name = serializers.CharField(source='assigned_user.full_name', read_only=True)
    assigned_user_email = serializers.EmailField(source='assigned_user.email', read_only=True)

    class Meta:
        model = TeamRoleAssignment
        fields = ['id', 'role_name', 'assigned_user_id', 'assigned_user_name', 'assigned_user_email', 'assigned_at']

    def validate(self, data):
        if self.instance and 'role_name' in data and data['role_name'] != self.instance.role_name:
            raise serializers.ValidationError(
                {"role_name": "A role assignment's role cannot be changed after creation — remove it and create a new one instead."}
            )
        role_name = data.get('role_name', self.instance.role_name if self.instance else None)

        if role_name == 'Admin':
            existing_admin = TeamRoleAssignment.objects.filter(role_name='Admin')
            if self.instance:
                existing_admin = existing_admin.exclude(pk=self.instance.pk)
            if existing_admin.exists():
                raise serializers.ValidationError(
                    {"role_name": "An Admin already exists — transfer the existing Admin seat instead of creating a new one."}
                )

        if 'assigned_user' in data and data['assigned_user'] is not None:
            assigned_user = data['assigned_user']
            conflicting = TeamRoleAssignment.objects.filter(assigned_user=assigned_user)
            if self.instance:
                conflicting = conflicting.exclude(pk=self.instance.pk)
            if conflicting.exists():
                raise serializers.ValidationError(
                    {"assigned_user_id": f"{assigned_user.email} already holds a Staff Role and cannot hold two at once."}
                )

        return data


class TeamUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email']