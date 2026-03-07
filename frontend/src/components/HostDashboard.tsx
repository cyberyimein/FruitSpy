import type { HostMetrics } from '../lib/types';

type Props = {
    host: HostMetrics;
};

type MetricCardProps = {
    title: string;
    value: string;
    percent: number;
    note: string;
};

function MetricCard({ title, value, percent, note }: MetricCardProps) {
    return (
        <article className="metric-card">
            <header className="metric-title">{title}</header>
            <div className="metric-value">{value}</div>
            <div className="metric-track" aria-hidden>
                <div className="metric-fill" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
            </div>
            <p className="metric-note">{note}</p>
        </article>
    );
}

export default function HostDashboard({ host }: Props) {
    return (
        <section className="panel">
            <div className="panel-head">
                <h2>Host Overview</h2>
            </div>
            <div className="metrics-grid">
                <MetricCard
                    title="CPU"
                    value={`${host.cpu_percent.toFixed(1)}%`}
                    percent={host.cpu_percent}
                    note="Current processor load"
                />
                <MetricCard
                    title="Memory"
                    value={`${host.memory_percent.toFixed(1)}%`}
                    percent={host.memory_percent}
                    note={`${host.memory_used_gb.toFixed(1)} GB of ${host.memory_total_gb.toFixed(1)} GB used`}
                />
                <MetricCard
                    title="Storage"
                    value={`${host.storage_percent.toFixed(1)}%`}
                    percent={host.storage_percent}
                    note={`${host.storage_used_gb.toFixed(1)} GB of ${host.storage_total_gb.toFixed(1)} GB used`}
                />
            </div>
        </section>
    );
}
