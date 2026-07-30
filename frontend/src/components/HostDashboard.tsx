import type { HostMetrics, RoomClimateStatus } from '../lib/types';

type Props = {
    host: HostMetrics;
    roomClimate: RoomClimateStatus;
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

function formatSampleAge(status: RoomClimateStatus) {
    if (status.age_seconds === null) {
        return status.state === 'scanning' ? 'Scanning for the first reading' : 'No reading received yet';
    }
    if (status.age_seconds < 60) {
        return `${status.age_seconds}s ago`;
    }
    return `${Math.floor(status.age_seconds / 60)}m ago`;
}

function RoomMetric({
    title,
    value,
    unit,
    note,
}: {
    title: string;
    value: string;
    unit: string;
    note: string;
}) {
    return (
        <article className="room-metric-card">
            <header className="metric-title">{title}</header>
            <div className="room-metric-value">
                <strong>{value}</strong>
                <span>{unit}</span>
            </div>
            <p className="metric-note">{note}</p>
        </article>
    );
}

export default function HostDashboard({ host, roomClimate }: Props) {
    const reading = roomClimate.reading;
    return (
        <>
            <section className="panel host-section">
                <div className="panel-head host-section-head">
                    <div>
                        <span className="section-kicker">Computer</span>
                        <h2>Mac mini</h2>
                    </div>
                    <span className="status-badge">live</span>
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

            <section className="panel host-section room-section">
                <div className="panel-head host-section-head">
                    <div>
                        <span className="section-kicker">Environment</span>
                        <h2>Room</h2>
                        <p>Latest SwitchBot reading. FruitSpy samples every 5 minutes and replaces the previous value.</p>
                    </div>
                    <span className={`status-badge ${roomClimate.state === 'stale' || roomClimate.state === 'unavailable' ? 'status-badge-danger' : ''}`}>
                        {roomClimate.state}
                    </span>
                </div>

                {roomClimate.error && !reading && <div className="panel-warning">{roomClimate.error}</div>}

                <div className="room-metrics-grid">
                    <RoomMetric
                        title="Temperature"
                        value={reading ? reading.temperature_c.toFixed(1) : '—'}
                        unit="°C"
                        note="Ambient temperature"
                    />
                    <RoomMetric
                        title="Humidity"
                        value={reading ? String(reading.humidity_percent) : '—'}
                        unit="% RH"
                        note="Relative humidity"
                    />
                    <RoomMetric
                        title="Carbon dioxide"
                        value={reading ? reading.co2_ppm.toLocaleString() : '—'}
                        unit="ppm"
                        note="Room CO₂ concentration"
                    />
                    <RoomMetric
                        title="Sensor battery"
                        value={reading?.battery_percent !== null && reading?.battery_percent !== undefined
                            ? String(reading.battery_percent)
                            : '—'}
                        unit="%"
                        note={`Sampled ${formatSampleAge(roomClimate)}`}
                    />
                </div>
            </section>
        </>
    );
}
