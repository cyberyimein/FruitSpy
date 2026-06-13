import { useState } from 'react';
import type { ContainerMetrics } from '../lib/types';

type Props = {
    containers: ContainerMetrics[];
    runtimeAvailable: boolean;
    runtimeError: string | null;
    runtimeName: string;
    controlEnabled: boolean;
};

function formatCpuLimit(cpus: number) {
    if (!Number.isFinite(cpus) || cpus <= 0) {
        return 'Limit unknown';
    }
    const value = Number.isInteger(cpus) ? cpus.toFixed(0) : cpus.toFixed(1);
    return `${value} ${cpus === 1 ? 'core' : 'cores'} max`;
}

function formatMemoryLimit(memoryMb: number) {
    if (!Number.isFinite(memoryMb) || memoryMb <= 0) {
        return 'Limit unknown';
    }
    if (memoryMb >= 1024) {
        return `${(memoryMb / 1024).toFixed(memoryMb % 1024 === 0 ? 0 : 1)} GiB max`;
    }
    return `${memoryMb.toFixed(0)} MiB max`;
}

function formatMemoryUsage(memoryMb: number) {
    if (!Number.isFinite(memoryMb) || memoryMb < 0) {
        return 'Unknown';
    }
    if (memoryMb >= 1024) {
        return `${(memoryMb / 1024).toFixed(2)} GiB`;
    }
    return `${memoryMb.toFixed(1)} MiB`;
}

export default function ContainerPanel({
    containers,
    runtimeAvailable,
    runtimeError,
    runtimeName,
    controlEnabled,
}: Props) {
    const [active, setActive] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [logsTitle, setLogsTitle] = useState('');
    const [loadingLogs, setLoadingLogs] = useState(false);
    const [logsExpanded, setLogsExpanded] = useState(false);
    const [actionInFlight, setActionInFlight] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);

    const runningCount = containers.filter((container) => container.status === 'running').length;

    async function openLogs(container: ContainerMetrics) {
        setActive(container.id);
        setLogsTitle(container.name);
        setLogsExpanded(false);
        setLoadingLogs(true);
        try {
            const response = await fetch(`/api/logs/${encodeURIComponent(container.id)}?tail=200`);
            const payload = (await response.json()) as { lines?: string[]; error?: string };
            if (!response.ok) {
                throw new Error(payload.error ?? `Failed to load logs for ${container.name}`);
            }
            setLogs(payload.lines ?? [payload.error ?? 'No logs returned']);
        } catch (error) {
            setLogs([
                error instanceof Error
                    ? error.message
                    : `Failed to load logs for ${container.name}`,
            ]);
        } finally {
            setLoadingLogs(false);
        }
    }

    async function runAction(container: ContainerMetrics, action: 'start' | 'stop' | 'restart') {
        const actionKey = `${container.id}:${action}`;
        setActionInFlight(actionKey);
        setActionError(null);
        try {
            const response = await fetch(`/api/containers/${encodeURIComponent(container.id)}/${action}`, {
                method: 'POST',
                headers: {
                    'X-FruitSpy-Control': '1',
                },
            });
            const payload = (await response.json()) as { detail?: string };
            if (!response.ok) {
                throw new Error(payload.detail ?? `Failed to ${action} ${container.name}`);
            }
        } catch (error) {
            setActionError(error instanceof Error ? error.message : `Failed to ${action} ${container.name}`);
        } finally {
            setActionInFlight(null);
        }
    }

    return (
        <section className="panel">
            <div className="panel-head panel-head-split">
                <div>
                    <h2>Containers</h2>
                    <p>{runningCount} running / {containers.length} total / {runtimeName}</p>
                </div>
                <span className={`status-badge ${runtimeAvailable ? '' : 'status-badge-danger'}`}>
                    {runtimeAvailable ? 'Runtime ready' : 'Runtime unavailable'}
                </span>
            </div>

            {!runtimeAvailable && (
                <div className="panel-warning">
                    {runtimeName} is unavailable on this host: {runtimeError ?? 'unknown error'}
                </div>
            )}

            {actionError && <div className="panel-warning">{actionError}</div>}

            {containers.length === 0 ? (
                <div className="empty-card">No containers found</div>
            ) : (
                <div className="container-list">
                    {containers.map((container) => (
                        <article key={container.id} className="container-row">
                            <div>
                                <div className="row-title-wrap">
                                    <h3>{container.name}</h3>
                                    <span className="status-badge">{container.status}</span>
                                </div>
                                <p className="row-sub">{container.image}</p>
                            </div>
                            <div className="mini-metric">
                                <span>CPU used</span>
                                <strong>
                                    {container.status === 'running' ? `${container.cpu_percent.toFixed(1)}%` : '--'}
                                </strong>
                                <small>{formatCpuLimit(container.cpu_limit)}</small>
                            </div>
                            <div className="mini-metric">
                                <span>
                                    Memory
                                    {container.status === 'running'
                                        ? ` · ${container.memory_percent.toFixed(1)}%`
                                        : ''}
                                </span>
                                <strong>
                                    {container.status === 'running'
                                        ? formatMemoryUsage(container.memory_used_mb)
                                        : '--'}
                                </strong>
                                <small>{formatMemoryLimit(container.memory_limit_mb)}</small>
                            </div>
                            <div className="row-actions">
                                {controlEnabled && container.status === 'running' && (
                                    <>
                                        <button
                                            className="text-btn"
                                            type="button"
                                            onClick={() => runAction(container, 'restart')}
                                            disabled={actionInFlight !== null}
                                        >
                                            {actionInFlight === `${container.id}:restart` ? 'Restarting...' : 'Restart'}
                                        </button>
                                        <button
                                            className="danger-btn"
                                            type="button"
                                            onClick={() => runAction(container, 'stop')}
                                            disabled={actionInFlight !== null}
                                        >
                                            {actionInFlight === `${container.id}:stop` ? 'Stopping...' : 'Stop'}
                                        </button>
                                    </>
                                )}
                                {controlEnabled && container.status === 'stopped' && (
                                    <button
                                        className="secondary-btn"
                                        type="button"
                                        onClick={() => runAction(container, 'start')}
                                        disabled={actionInFlight !== null}
                                    >
                                        {actionInFlight === `${container.id}:start` ? 'Starting...' : 'Start'}
                                    </button>
                                )}
                                <button
                                    className="text-btn"
                                    type="button"
                                    onClick={() => openLogs(container)}
                                    disabled={loadingLogs && active === container.id}
                                >
                                    {loadingLogs && active === container.id ? 'Loading...' : 'View Logs'}
                                </button>
                            </div>
                        </article>
                    ))}
                </div>
            )}

            {active && (
                <section className={`logs-drawer ${logsExpanded ? 'logs-drawer-expanded' : ''}`}>
                    <div className="logs-head">
                        <h3>Recent Logs: {logsTitle}</h3>
                        <div className="logs-actions">
                            <button className="text-btn" type="button" onClick={() => setLogsExpanded((prev) => !prev)}>
                                {logsExpanded ? 'Normal Width' : 'Expand Width'}
                            </button>
                            <button
                                className="text-btn"
                                type="button"
                                onClick={() => {
                                    setActive(null);
                                    setLogsExpanded(false);
                                }}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                    <pre>{logs.join('\n')}</pre>
                </section>
            )}
        </section>
    );
}
