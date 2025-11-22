# Integración con Astro — Ejemplos

Este archivo contiene ejemplos de cómo Astro puede interactuar con la API para:
- pedir tipos de instancia disponibles según vCPU/RAM
- crear un grupo de nodos (número de nodos, tipo de instancia, imagen)
- obtener la IP y la contraseña devuelta por el backend

Nota: la API espera rutas como `http://<backend_host>:8001`.

1) Obtener tipos de instancia GCP (GET)

Ejemplo (Astro hace un GET):

```
GET /instance-types/gcp?zone=europe-west1-b&cpus=2&ram_gb=4
Host: 127.0.0.1:8001
```

Respuesta (ejemplo):

```json
{
  "success": true,
  "count": 3,
  "instance_types": [
    {"name":"e2-standard-2","cpus":2,"ram_gb":4.0,"description":"..."},
    {"name":"n1-standard-2","cpus":2,"ram_gb":4.0,"description":"..."}
  ]
}
```

2) Obtener tipos de instancia AWS (GET)

Ejemplo (Astro hace un GET):

```
GET /instance-types/aws?min_vcpus=2&min_memory_gb=4
Host: 127.0.0.1:8001
```

Respuesta (ejemplo):

```json
{
  "success": true,
  "count": 5,
  "instance_types": [
    {"instance_type":"t3.large","vcpus":2,"memory_gb":8.0},
    {"instance_type":"m5.large","vcpus":2,"memory_gb":8.0}
  ]
}
```

3) Crear N nodos en GCP (POST -> `/create`):

Astro puede POSTear a `/create` enviando `count`, `machine_type`, y `image_project`/`image_family` o `image`.
Ejemplo body JSON:

```json
{
  "credentials": "./credentials.json",
  "zone": "europe-west1-b",
  "name": "t3-mycluster",
  "machine_type": "e2-medium",
  "count": 3,
  "image_project": "ubuntu-os-cloud",
  "image_family": "ubuntu-2204-lts"
}
```

Respuesta (ejemplo):

```json
{
  "success": true,
  "created": [
    {"success": true, "name": "t3-mycluster-1", "public_ip": "34.x.x.x", "password": "Abc123...", "username": "ubuntu"},
    {"success": true, "name": "t3-mycluster-2", "public_ip": "34.x.x.y", "password": "Zyx987...", "username": "ubuntu"}
  ]
}
```

4) Crear N nodos en AWS (POST `/aws/create`):

Astro POST a `/aws/create` con `min_count`/`max_count` o `min_count == max_count == count` y `instance_type`.
Ejemplo body JSON:

```json
{
  "region": "us-west-2",
  "name": "mi-cluster-aws",
  "instance_type": "t3.medium",
  "min_count": 3,
  "max_count": 3
}
```

Respuesta (ejemplo):

```json
{
  "success": true,
  "created": [
    {"InstanceId":"i-0123","Name":"t3-mi-cluster-aws","PublicIpAddress":"3.x.x.x","Password":"...","username":"ubuntu"}
  ]
}
```


Código de ejemplo (Astro/JS) usando fetch:

```js
// obtener tipos GCP
const res = await fetch('http://127.0.0.1:8001/instance-types/gcp?zone=europe-west1-b&cpus=2&ram_gb=4');
const data = await res.json();
console.log(data.instance_types);

// crear 3 nodos GCP
const createRes = await fetch('http://127.0.0.1:8001/create', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    credentials: './credentials.json',
    zone: 'europe-west1-b',
    name: 't3-mycluster',
    machine_type: 'e2-medium',
    count: 3,
    image_project: 'ubuntu-os-cloud',
    image_family: 'ubuntu-2204-lts'
  })
});
const createData = await createRes.json();
console.log(createData);
```
