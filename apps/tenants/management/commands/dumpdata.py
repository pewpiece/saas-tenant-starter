from django.core.management import CommandError
from django.core.management.commands import dumpdata

from apps.tenants.context import tenant_context
from apps.tenants.models import Organization


class Command(dumpdata.Command):
    """Django's dumpdata, made to work with tenant-scoped default managers.

    Without --org, every model is read through its base manager (as with
    --all), so tenant-owned tables are dumped for every organization instead
    of raising NoActiveTenantError.

    With --org=<slug>, the dump runs inside tenant_context(org): tenant-owned
    tables contain only that organization's rows. Tables that are not
    tenant-owned (users, organizations, ...) are not filtered, so pass the
    app labels of tenant-owned models when exporting one tenant.
    """

    help = dumpdata.Command.help + " Supports --org to export one tenant's tenant-owned rows."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--org",
            help="Only dump tenant-owned rows of the organization with this slug.",
        )

    def handle(self, *app_labels, **options):
        slug = options.pop("org", None)
        if slug is None:
            options["use_base_manager"] = True
            return super().handle(*app_labels, **options)

        try:
            org = Organization.objects.get(slug=slug)
        except Organization.DoesNotExist as exc:
            raise CommandError(f"No organization with slug {slug!r}.") from exc
        options["use_base_manager"] = False
        with tenant_context(org):
            return super().handle(*app_labels, **options)
