from django.db import migrations, models


LEGACY_ADMIN_ROLE = 'CRM Administrator'
LEGACY_ROLES_TO_DROP = ['Operations Manager', 'Sales Manager', 'Finance Manager', 'Business Analyst']


def consolidate_roles(apps, schema_editor):
    TeamRoleAssignment = apps.get_model('accounts', 'TeamRoleAssignment')

    # The old "CRM Administrator" seat becomes the new single "Admin" seat.
    TeamRoleAssignment.objects.filter(role_name=LEGACY_ADMIN_ROLE).update(role_name='Admin')

    # The other legacy management roles have no equivalent — drop them.
    # Any user who held one simply has no role until an Admin assigns them
    # as the new Booking Manager.
    TeamRoleAssignment.objects.filter(role_name__in=LEGACY_ROLES_TO_DROP).delete()


def revert_roles(apps, schema_editor):
    TeamRoleAssignment = apps.get_model('accounts', 'TeamRoleAssignment')
    TeamRoleAssignment.objects.filter(role_name='Admin').update(role_name=LEGACY_ADMIN_ROLE)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_emailotp'),
    ]

    operations = [
        migrations.RunPython(consolidate_roles, revert_roles),
        migrations.AlterField(
            model_name='teamroleassignment',
            name='role_name',
            field=models.CharField(
                choices=[('Admin', 'Admin'), ('Booking Manager', 'Booking Manager')],
                max_length=100,
                unique=True,
            ),
        ),
    ]
