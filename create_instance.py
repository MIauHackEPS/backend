#!/usr/bin/env python3
"""
Script simple para crear una instancia de GCP
"""
import argparse
import json
import os
import secrets
import string
from google.cloud import compute_v1


def sanitize_gcp_name(name: str) -> str:
    """Sanitize a name to be a valid GCP instance name.

    Rules enforced:
    - lowercase
    - only letters, numbers and hyphens
    - replace invalid chars with hyphen
    - collapse consecutive hyphens
    - trim to 63 chars
    - must start with a letter, if not, prefix with 'a'
    - must end with letter or number (remove trailing hyphens)
    """
    if not name:
        return name
    s = name.lower()
    # replace invalid chars with hyphen
    import re
    s = re.sub(r'[^a-z0-9-]', '-', s)
    # collapse multiple hyphens
    s = re.sub(r'-{2,}', '-', s)
    # trim to 63 chars
    s = s[:63]
    # remove leading/trailing hyphens
    s = s.strip('-')
    if not s:
        s = 'a'
    # must start with a letter
    if not s[0].isalpha():
        s = 'a' + s
        # ensure length
        s = s[:63]
    # ensure ends with alnum
    while not s[-1].isalnum():
        s = s[:-1]
        if not s:
            s = 'a'
            break
    return s


def create_instance(project_id, zone, instance_name, machine_type, ssh_key=None, password: str = None, count: int = 1, image_project: str = None, image_family: str = None, image: str = None):
    """
    Crea una instancia de GCP
    
    Args:
        project_id: ID del proyecto de GCP
        zone: Zona de GCP (ej: us-central1-a)
        instance_name: Nombre de la instancia a crear
        machine_type: Tipo de máquina (ej: e2-medium, n1-standard-1)
        ssh_key: Clave SSH pública para acceso (opcional)
    """
    print(f"Creando instancia '{instance_name}' en zona: {zone}")
    print(f"Tipo de máquina: {machine_type}")
    if ssh_key:
        print(f"Clave SSH: configurada")    
    
    # Cliente de compute
    instance_client = compute_v1.InstancesClient()
    
    # Sanitize instance name for GCP (GCP names cannot contain underscores)
    safe_name = sanitize_gcp_name(instance_name)
    if safe_name != instance_name:
        print(f"Nota: el nombre solicitado '{instance_name}' ha sido sanitizado a '{safe_name}' para cumplir las reglas de nombres de GCP.")

    results = []

    # Prepare disk image source
    if image:
        source_image = image
    elif image_project and image_family:
        source_image = f"projects/{image_project}/global/images/family/{image_family}"
    else:
        # default to Debian 11
        source_image = "projects/debian-cloud/global/images/family/debian-11"

    # Configure a basic network interface used for all instances
    network_interface = compute_v1.NetworkInterface()
    network_interface.name = "global/networks/default"
    access_config = compute_v1.AccessConfig()
    access_config.name = "External NAT"
    access_config.type_ = "ONE_TO_ONE_NAT"
    network_interface.access_configs = [access_config]
    
    # Configurar metadata (SSH keys o startup script para password)
    metadata = compute_v1.Metadata()
    items = []
    if ssh_key:
        metadata_item = compute_v1.Items()
        metadata_item.key = "ssh-keys"
        metadata_item.value = ssh_key
        items.append(metadata_item)

    # Always generate a random password for the instance (ignore any provided password)
    alphabet = string.ascii_letters + string.digits + "!@#$%&*()-_=+"
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(14))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%&*()-_=+" for c in pw)):
            password = pw
            break

    # Build startup script to set password and enable password SSH auth
    if password:
        # Build startup script to set password and enable password SSH auth
        startup = f"""#!/bin/bash
set -e
if id -u ubuntu >/dev/null 2>&1; then
    echo "ubuntu:{password}" | chpasswd
else
    useradd -m -s /bin/bash ubuntu || true
    echo "ubuntu:{password}" | chpasswd
fi
sed -i 's/^#PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
systemctl restart sshd || service ssh restart || true
"""
        metadata_item2 = compute_v1.Items()
        metadata_item2.key = "startup-script"
        metadata_item2.value = startup
        items.append(metadata_item2)

    try:
        operation_client = compute_v1.ZoneOperationsClient()

        # Create instances sequentially so each gets its own random password and startup script
        for idx in range(max(1, int(count or 1))):
            # build per-instance name
            this_name = safe_name
            if count and int(count) > 1:
                suffix = f"-{idx+1}"
                # ensure name length <=63
                trunc = this_name[:(63 - len(suffix))]
                this_name = f"{trunc}{suffix}"

            # Per-instance password generation
            alphabet = string.ascii_letters + string.digits + "!@#$%&*()-_=+"
            while True:
                pw = ''.join(secrets.choice(alphabet) for _ in range(14))
                if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                        and any(c.isdigit() for c in pw) and any(c in "!@#$%&*()-_=+" for c in pw)):
                    instance_password = pw
                    break

            # Build instance resource
            instance = compute_v1.Instance()
            instance.name = this_name
            instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"

            # Disk
            disk = compute_v1.AttachedDisk()
            disk.boot = True
            disk.auto_delete = True
            disk.initialize_params = compute_v1.AttachedDiskInitializeParams()
            disk.initialize_params.source_image = source_image
            disk.initialize_params.disk_size_gb = 10
            instance.disks = [disk]

            instance.network_interfaces = [network_interface]

            # Metadata: ssh keys + startup script
            md_items = list(items)  # base items collected earlier (e.g. ssh-keys if provided)

            startup = f"""#!/bin/bash
set -e
if id -u ubuntu >/dev/null 2>&1; then
    echo "ubuntu:{instance_password}" | chpasswd
else
    useradd -m -s /bin/bash ubuntu || true
    echo "ubuntu:{instance_password}" | chpasswd
fi
sed -i 's/^#PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
systemctl restart sshd || service ssh restart || true
"""
            md_start = compute_v1.Items()
            md_start.key = "startup-script"
            md_start.value = startup
            md_items.append(md_start)

            if md_items:
                md = compute_v1.Metadata()
                md.items = md_items
                instance.metadata = md

            # Insert the instance
            request = compute_v1.InsertInstanceRequest()
            request.project = project_id
            request.zone = zone
            request.instance_resource = instance

            print(f"\nEnviando solicitud de creación para {this_name}...")
            op = instance_client.insert(request=request)

            # Wait for operation to complete
            while op.status != compute_v1.Operation.Status.DONE:
                op = operation_client.get(project=project_id, zone=zone, operation=op.name)

            if op.error:
                print(f"Error creando {this_name}: {op.error}")
                results.append({"success": False, "name": this_name, "error": "; ".join([e.message for e in (op.error.errors or [])])})
                continue

            # Fetch created instance info
            instance_info = instance_client.get(project=project_id, zone=zone, instance=this_name)
            public_ip = None
            for iface in instance_info.network_interfaces:
                if iface.access_configs:
                    for ac in iface.access_configs:
                        ip = getattr(ac, 'nat_i_p', None) or getattr(ac, 'nat_ip', None)
                        if ip:
                            public_ip = ip

            results.append({"success": True, "name": this_name, "public_ip": public_ip, "password": instance_password, "username": "ubuntu"})

        # Return list of created instances (or single dict if only one)
        if len(results) == 1:
            return results[0]
        return {"success": True, "created": results}

    except Exception as e:
        print(f"\n❌ Error al crear la instancia(s): {e}")
        return {"success": False, "error": str(e)}