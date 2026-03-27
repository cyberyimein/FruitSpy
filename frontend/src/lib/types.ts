export type HostMetrics = {
    cpu_percent: number;
    memory_percent: number;
    memory_used_gb: number;
    memory_total_gb: number;
    storage_percent: number;
    storage_used_gb: number;
    storage_total_gb: number;
};

export type ContainerMetrics = {
    id: string;
    name: string;
    image: string;
    status: string;
    cpu_percent: number;
    memory_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
};

export type Snapshot = {
    timestamp: number;
    host: HostMetrics;
    containers: ContainerMetrics[];
    docker_available: boolean;
    docker_error: string | null;
};

export type RuntimeConfig = {
    portainer_url: string;
    refresh_seconds: number;
    logs_tail_default: number;
};

export type PackageRecord = {
    manager: string;
    name: string;
    version: string;
    source: string;
};

export type PackageManagerInventory = {
    manager: string;
    available: boolean;
    command: string | null;
    package_count: number;
    error: string | null;
    packages: PackageRecord[];
};

export type PackageInventory = {
    timestamp: number;
    total_packages: number;
    managers: PackageManagerInventory[];
};
