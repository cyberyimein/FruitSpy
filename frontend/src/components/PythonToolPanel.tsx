import { useEffect, useState } from 'react';
import type { PythonToolStatus } from '../lib/types';

type ApiError = {
    error?: {
        message?: string;
    };
};

function formatCpu(value: number) {
    return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function formatLastRun(status: PythonToolStatus) {
    if (!status.last_execution) {
        return 'No runs yet';
    }
    const finished = new Date(status.last_execution.finished_at).toLocaleTimeString();
    return `${status.last_execution.status} · ${status.last_execution.duration_ms} ms · ${finished}`;
}

export default function PythonToolPanel() {
    const [status, setStatus] = useState<PythonToolStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [changing, setChanging] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function loadStatus(background = false) {
        if (!background) {
            setLoading(true);
        }
        try {
            const response = await fetch('/api/v1/tools/python');
            if (!response.ok) {
                throw new Error(`Python Tool status request failed: ${response.status}`);
            }
            const payload = (await response.json()) as PythonToolStatus;
            setStatus(payload);
            setError(null);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : 'Unable to load Python Tool status');
        } finally {
            if (!background) {
                setLoading(false);
            }
        }
    }

    useEffect(() => {
        void loadStatus();
        const timer = window.setInterval(() => void loadStatus(true), 3000);
        return () => window.clearInterval(timer);
    }, []);

    async function toggleEnabled() {
        if (!status || changing) {
            return;
        }
        setChanging(true);
        setError(null);
        try {
            const response = await fetch('/api/v1/tools/python/enabled', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-FruitSpy-Control': '1',
                },
                body: JSON.stringify({ enabled: !status.enabled }),
            });
            const payload = (await response.json()) as PythonToolStatus & ApiError;
            if (!response.ok) {
                throw new Error(payload.error?.message ?? `Python Tool update failed: ${response.status}`);
            }
            setStatus(payload);
        } catch (updateError) {
            setError(updateError instanceof Error ? updateError.message : 'Unable to update Python Tool');
        } finally {
            setChanging(false);
        }
    }

    if (loading && !status) {
        return <div className="empty-card">Loading Python Tool status...</div>;
    }

    if (!status) {
        return (
            <section className="panel">
                <div className="panel-warning">{error ?? 'Python Tool status is unavailable.'}</div>
            </section>
        );
    }

    const isTransitioning = changing || status.state === 'checking' || status.state === 'disabling';
    const statusIsDanger = status.state === 'degraded';

    return (
        <section className="panel">
            <article className="python-tool-card">
                <div className="python-tool-head">
                    <div>
                        <div className="row-title-wrap">
                            <h2>Python Tool</h2>
                            <span className={`status-badge ${statusIsDanger ? 'status-badge-danger' : ''}`}>
                                {status.state}
                            </span>
                        </div>
                        <p>
                            Runs Anomalo Python calls in a fresh Apple container sandbox. Execution is restricted to
                            this Mac through loopback or the configured Anomalo container network.
                        </p>
                    </div>
                    <button
                        className={status.enabled ? 'danger-btn' : 'primary-btn'}
                        type="button"
                        onClick={() => void toggleEnabled()}
                        disabled={isTransitioning}
                    >
                        {changing
                            ? 'Updating...'
                            : status.state === 'checking'
                                ? 'Checking...'
                                : status.enabled
                                    ? 'Disable'
                                    : 'Enable'}
                    </button>
                </div>

                {(error || status.error) && (
                    <div className="panel-warning">{error ?? status.error}</div>
                )}

                <div className="python-tool-metrics">
                    <div>
                        <span>Sandbox image</span>
                        <strong>{status.image}</strong>
                    </div>
                    <div>
                        <span>Compute limit</span>
                        <strong>{formatCpu(status.limits.cpu_count)} CPU · {status.limits.memory_mb} MiB</strong>
                    </div>
                    <div>
                        <span>Execution limit</span>
                        <strong>{status.limits.timeout_ms / 1000}s · {status.limits.max_concurrency} concurrent</strong>
                    </div>
                    <div>
                        <span>Active runs</span>
                        <strong>{status.running_executions}</strong>
                    </div>
                </div>

                <div className="python-tool-foot">
                    <span>Last execution</span>
                    <strong>{formatLastRun(status)}</strong>
                    <small>
                        Read-only root · non-root user · no DNS · internal network · {status.limits.max_output_chars.toLocaleString()} character output cap
                    </small>
                </div>
            </article>
        </section>
    );
}
