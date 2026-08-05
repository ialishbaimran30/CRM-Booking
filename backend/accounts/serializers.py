from rest_framework import serializers


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
