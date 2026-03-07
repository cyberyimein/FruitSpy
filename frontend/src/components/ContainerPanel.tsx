import { useState } from 'react';
import type { ContainerMetrics } from '../lib/types';

type Props = {
    containers: ContainerMetrics[];
    dockerAvailable: boolean;
    dockerError: string | null;
    portainerUrl: string;
};

export default function ContainerPanel({
    containers,
    dockerAvailable,
    dockerError,
    portainerUrl,
}: Props) {
    const [active, setActive] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [logsTitle, setLogsTitle] = useState('');
    const [loadingLogs, setLoadingLogs] = useState(false);
    const [logsExpanded, setLogsExpanded] = useState(false);

    async function openLogs(container: ContainerMetrics) {
        setActive(container.id);
        setLogsTitle(container.name);
        setLogsExpanded(false);
        setLoadingLogs(true);
        const response = await fetch(`/api/logs/${container.id}?tail=200`);
        const payload = (await response.json()) as { lines?: string[]; error?: string };
        setLoadingLogs(false);
        setLogs(payload.lines ?? [payload.error ?? 'Failed to load logs']);
    }

    return (
        <section className="panel">
            <div className="panel-head panel-head-split">
                <div>
                    <h2>Running Containers</h2>
                    <p>{containers.length} running</p>
                </div>
                <a className="secondary-btn" href={portainerUrl} target="_blank" rel="noreferrer">
                    Open in Portainer
                </a>
            </div>

            {!dockerAvailable && (
                <div className="panel-warning">Docker is unavailable on this host: {dockerError ?? 'unknown error'}</div>
            )}

            {containers.length === 0 ? (
                <div className="empty-card">No running containers</div>
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
                                <span>CPU</span>
                                <strong>{container.cpu_percent.toFixed(1)}%</strong>
                            </div>
                            <div className="mini-metric">
                                <span>Memory</span>
                                <strong>{container.memory_percent.toFixed(1)}%</strong>
                            </div>
                            <div className="row-actions">
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
