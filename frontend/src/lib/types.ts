export type HostMetrics = {
    cpu_percent: number;
    memory_percent: number;
    memory_used_gb: number;
    memory_total_gb: number;
    storage_percent: number;
    storage_used_gb: number;
    storage_total_gb: number;
};

export type RoomClimateReading = {
    observed_at: number;
    observed_at_iso: string;
    device_id: string;
    temperature_c: number;
    humidity_percent: number;
    co2_ppm: number;
    battery_percent: number | null;
    rssi: number;
};

export type RoomClimateStatus = {
    state: 'scanning' | 'ready' | 'stale' | 'unavailable';
    reading: RoomClimateReading | null;
    stale: boolean;
    age_seconds: number | null;
    interval_seconds: number;
    scan_seconds: number;
    last_attempt_at: number | null;
    next_scan_at: number | null;
    error: string | null;
};

export type ContainerMetrics = {
    id: string;
    name: string;
    image: string;
    status: string;
    cpu_percent: number;
    cpu_limit: number;
    memory_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
};

export type Snapshot = {
    timestamp: number;
    host: HostMetrics;
    room_climate: RoomClimateStatus;
    containers: ContainerMetrics[];
    runtime_name: string;
    runtime_available: boolean;
    runtime_error: string | null;
};

export type RuntimeConfig = {
    runtime_name: string;
    container_control_enabled: boolean;
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

export type PythonToolState = 'disabled' | 'checking' | 'ready' | 'busy' | 'degraded' | 'disabling';

export type PythonToolStatus = {
    schema_version: number;
    id: string;
    enabled: boolean;
    state: PythonToolState;
    ready: boolean;
    image: string;
    limits: {
        cpu_count: number;
        memory_mb: number;
        timeout_ms: number;
        max_code_bytes: number;
        max_output_chars: number;
        max_concurrency: number;
        max_artifacts: number;
        max_artifact_bytes: number;
        max_artifact_total_bytes: number;
        artifact_ttl_seconds: number;
    };
    running_executions: number;
    last_execution: {
        finished_at: string;
        status: 'succeeded' | 'failed' | 'timed_out';
        duration_ms: number;
    } | null;
    error: string | null;
};

export type CrawlToolState = 'disabled' | 'checking' | 'ready' | 'busy' | 'degraded' | 'disabling';

export type CrawlToolStatus = {
    schema_version: number;
    id: string;
    enabled: boolean;
    state: CrawlToolState;
    ready: boolean;
    authentication_configured: boolean;
    running_executions: number;
    queued_executions: number;
    limits: {
        max_concurrency: number;
        max_queue: number;
        timeout_ms: number;
        max_timeout_ms: number;
        max_redirects: number;
        max_response_bytes: number;
        max_html_bytes: number;
    };
    error: string | null;
};

export type CrawlResult = {
    schema_version: number;
    crawl_id: string;
    ok: boolean;
    url: string;
    final_url: string;
    title: string;
    markdown: string;
    status_code: number;
    rendered: boolean;
    content_type: string;
    timings: {
        queue_ms: number;
        navigation_ms: number;
        render_ms: number;
        extract_ms: number;
        total_ms: number;
    };
    metrics: {
        html_bytes: number;
        markdown_chars: number;
        links_seen: number;
    };
    warnings: string[];
};

export type RoomClimateMcpStatus = {
    schema_version: number;
    id: string;
    name: string;
    tool_name: string;
    protocol_mode: 'modern' | 'legacy';
    protocol_version: '2026-07-28' | '2025-11-25';
    endpoint: string;
    authentication_configured: boolean;
    climate: RoomClimateStatus;
};
