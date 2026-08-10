from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_simplify_team_roles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teamroleassignment',
            name='role_name',
            field=models.CharField(
                choices=[('Admin', 'Admin'), ('Booking Manager', 'Booking Manager')],
                max_length=100,
            ),
        ),
        migrations.AddConstraint(
            model_name='teamroleassignment',
            constraint=models.UniqueConstraint(
                condition=Q(('role_name', 'Admin')),
                fields=('role_name',),
                name='accounts_single_admin_seat',
            ),
        ),
        migrations.AddConstraint(
            model_name='teamroleassignment',
            constraint=models.UniqueConstraint(
                condition=Q(('assigned_user__isnull', False)),
                fields=('role_name', 'assigned_user'),
                name='accounts_unique_role_per_user',
            ),
        ),
    ]
