#!/usr/bin/env python3
"""
Script para listar todas las instancias de GCP en un proyecto (rápido con aggregated_list)
"""
import argparse
import json
import os
from google.cloud import compute_v1


def list_instances(project_id: str, zone: str | None = None, team_name: str | None = None, state: str | None = None):
    """
    Lista instancias de Compute Engine en el proyecto.

    Args:
        project_id: ID del proyecto de GCP
        zone: Zona concreta (opcional). Si se especifica, solo muestra esa zona.
        team_name: Prefijo de nombre de instancia (opcional). Ej: "team1"
    """
    instance_client = compute_v1.InstancesClient()

    # Filtro server-side (opcional)
    # Ojo: en filtros de Compute usa "eq" y regex tipo RE2.
    # Ej: name eq "team1-.*"
    filter_expr = None
    if team_name:
        filter_expr = f'name eq "{team_name}-.*"'  # prefijo team_name-
        # Nota: filtros complejos con AND/OR a veces fallan; mejor simple. :contentReference[oaicite:1]{index=1}

    print("Listando instancias (aggregated_list)...\n")

    request = compute_v1.AggregatedListInstancesRequest(
        project=project_id,
        filter=filter_expr,
        return_partial_success=True  # recomendado si hay muchas instancias :contentReference[oaicite:2]{index=2}
    )

    total = 0
    all_instances = []

    for zone_key, scoped_list in instance_client.aggregated_list(request=request):
        # zone_key viene tipo "zones/us-central1-a"
        zone_name = zone_key.split("/")[-1]

        if zone and zone_name != zone:
            continue

        instances = scoped_list.instances
        if not instances:
            continue

        # If a state filter is provided, apply it client-side
        if state:
            filtered = [inst for inst in instances if getattr(inst, 'status', '').upper() == state.upper()]
        else:
            filtered = instances

        if not filtered:
            continue

        print(f"═══ Zona: {zone_name} ({len(filtered)} instancia(s)) ═══")
        print_instances(filtered, zone_name)
        print()

        all_instances.extend(filtered)
        total += len(filtered)

    if total == 0:
        msg = "No se encontraron instancias"
        if zone:
            msg += f" en la zona {zone}"
        if team_name:
            msg += f" con prefijo {team_name}-"
        print(msg)
    else:
        print(f"\n{'='*60}")
        print(f"TOTAL: {total} instancia(s) en el proyecto")
        print(f"{'='*60}")

    return all_instances


def print_instances(instances, zone):
    for instance in instances:
        status_emoji = (
            "🟢" if instance.status == "RUNNING"
            else "🔴" if instance.status == "TERMINATED"
            else "🟡"
        )

        print(f"{status_emoji} Nombre: {instance.name}")
        print(f"   Estado: {instance.status}")
        print(f"   Tipo de máquina: {instance.machine_type.split('/')[-1]}")
        print(f"   Zona: {zone}")

        if instance.network_interfaces:
            for iface in instance.network_interfaces:
                if iface.network_i_p:
                    print(f"   IP interna: {iface.network_i_p}")
                if iface.access_configs:
                    for ac in iface.access_configs:
                        if ac.nat_i_p:
                            print(f"   IP pública: {ac.nat_i_p}")

        if instance.disks:
            disk_info = ["boot" for d in instance.disks if d.boot]
            if disk_info:
                print(f"   Discos: {', '.join(disk_info)}")

        if instance.creation_timestamp:
            print(f"   Creada: {instance.creation_timestamp}")

        print()


def main():
    parser = argparse.ArgumentParser(description="Listar instancias de GCP")
    parser.add_argument("--credentials", required=True, help="Ruta al JSON de credenciales")
    parser.add_argument("--zone", help="Zona (ej: us-central1-a)")
    parser.add_argument("--team-name", help="Prefijo para filtrar instancias (ej: team1)")
    args = parser.parse_args()

    print(f"Cargando credenciales desde: {args.credentials}\n")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.credentials

    with open(args.credentials, "r") as f:
        credentials = json.load(f)

    list_instances(
        project_id=credentials["project_id"],
        zone=args.zone,
        team_name=args.team_name
    )


if __name__ == "__main__":
    main()
