from decimal import Decimal

from django.db import migrations

DEFAULT_SERVICES = [
    {
        "name": "Consultation",
        "hourly_rate": Decimal("50.00"),
        "description": "A general consultation session to discuss your needs and next steps.",
    },
    {
        "name": "Business Consultation",
        "hourly_rate": Decimal("75.00"),
        "description": "Guidance on business strategy, operations, and growth planning.",
    },
    {
        "name": "Technical Consultation",
        "hourly_rate": Decimal("80.00"),
        "description": "Expert technical guidance on systems, architecture, or engineering problems.",
    },
    {
        "name": "Training Session",
        "hourly_rate": Decimal("60.00"),
        "description": "A focused, hands-on training session on a specific skill or topic.",
    },
    {
        "name": "Strategy Session",
        "hourly_rate": Decimal("70.00"),
        "description": "Collaborative planning session to define goals and a strategic roadmap.",
    },
    {
        "name": "One-on-One Meeting",
        "hourly_rate": Decimal("40.00"),
        "description": "A private, individual meeting for personalized discussion.",
    },
    {
        "name": "Workshop",
        "hourly_rate": Decimal("100.00"),
        "description": "An interactive group session covering a specific subject in depth.",
    },
]


def seed_default_services(apps, schema_editor):
    Service = apps.get_model("booking", "Service")
    for entry in DEFAULT_SERVICES:
        # get_or_create: never overwrites a rate/description an Admin has
        # already customized for a service with this name.
        Service.objects.get_or_create(
            name=entry["name"],
            defaults={
                "hourly_rate": entry["hourly_rate"],
                "description": entry["description"],
                "is_active": True,
            },
        )


def remove_default_services(apps, schema_editor):
    Service = apps.get_model("booking", "Service")
    Service.objects.filter(name__in=[entry["name"] for entry in DEFAULT_SERVICES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0004_service_description"),
    ]

    operations = [
        migrations.RunPython(seed_default_services, remove_default_services),
    ]
