from rest_framework import serializers
from .models import TeamRoleAssignment
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
User = get_user_model()




class GoogleSignInSerializer(serializers.Serializer):
    id_token = serializers.CharField(write_only=True, trim_whitespace=True, max_length=10000)

    def validate_id_token(self, value):
        if not value:
            raise serializers.ValidationError("Google ID token is required.")
        return value


class AuthenticatedUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    profile_picture_url = serializers.URLField(read_only=True, allow_blank=True)


class TeamRoleSerializer(serializers.ModelSerializer):
    assigned_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='assigned_user', allow_null=True, required=False
    )
    assigned_user_name = serializers.CharField(source='assigned_user.full_name', read_only=True)
    assigned_user_email = serializers.EmailField(source='assigned_user.email', read_only=True)

    class Meta:
        model = TeamRoleAssignment
        fields = ['id', 'role_name', 'assigned_user_id', 'assigned_user_name', 'assigned_user_email', 'assigned_at']


class TeamUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email']