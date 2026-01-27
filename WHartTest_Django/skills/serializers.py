from pathlib import Path
from django.conf import settings
from rest_framework import serializers
from .models import Skill


class SkillSerializer(serializers.ModelSerializer):
    """Skill 序列化器"""
    creator_name = serializers.CharField(source='creator.username', read_only=True, allow_null=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    script_path = serializers.SerializerMethodField()

    class Meta:
        model = Skill
        fields = [
            'id', 'name', 'description', 'skill_content',
            'skill_path', 'script_path', 'is_active',
            'project', 'project_name',
            'creator', 'creator_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'name', 'description', 'skill_content',
            'skill_path', 'creator', 'creator_name',
            'project_name', 'created_at', 'updated_at'
        ]

    def get_script_path(self, obj):
        script_path = obj.get_script_path()
        if not script_path:
            return None
        try:
            media_root = Path(settings.MEDIA_ROOT).resolve(strict=False)
            candidate = Path(script_path).resolve(strict=False)
            rel = candidate.relative_to(media_root)
            return str(rel).replace('\\', '/')
        except Exception:
            return None


class SkillUploadSerializer(serializers.Serializer):
    """Skill 上传序列化器"""
    file = serializers.FileField(
        help_text='包含 SKILL.md 的 zip 文件'
    )

    def validate_file(self, value):
        if not value.name.endswith('.zip'):
            raise serializers.ValidationError('只支持 .zip 文件')
        if value.size > 10 * 1024 * 1024:  # 10MB
            raise serializers.ValidationError('文件大小不能超过 10MB')
        return value


class SkillGitImportSerializer(serializers.Serializer):
    """从 Git 仓库导入 Skill 的序列化器"""
    git_url = serializers.URLField(
        help_text='Git 仓库 HTTPS URL'
    )
    branch = serializers.CharField(
        required=False,
        default='main',
        allow_blank=True,
        max_length=256,
        help_text='分支名（默认 main）'
    )

    def validate_git_url(self, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != 'https':
            raise serializers.ValidationError('仅支持 HTTPS 协议')
        if not parsed.hostname:
            raise serializers.ValidationError('无效的仓库地址')
        return value

    def validate_branch(self, value):
        import re
        value = (value or '').strip()
        if not value:
            return 'main'
        if value.startswith('-'):
            raise serializers.ValidationError('分支名不能以 - 开头')
        if not re.match(r'^[a-zA-Z0-9_./-]+$', value):
            raise serializers.ValidationError('分支名包含非法字符')
        return value


class SkillListSerializer(serializers.ModelSerializer):
    """Skill 列表序列化器（轻量）"""
    creator_name = serializers.CharField(source='creator.username', read_only=True, allow_null=True)

    class Meta:
        model = Skill
        fields = [
            'id', 'name', 'description', 'is_active',
            'creator_name', 'created_at'
        ]


class SkillToggleSerializer(serializers.ModelSerializer):
    """Skill 启用/禁用切换序列化器"""

    class Meta:
        model = Skill
        fields = ['is_active']
