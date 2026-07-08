import { useEffect, useMemo, useState } from 'react';
import ConnectionIndicator from './components/ConnectionIndicator';
import ContainerPanel from './components/ContainerPanel';
import HostDashboard from './components/HostDashboard';
import PackageInventoryPanel from './components/PackageInventoryPanel';
import { DashboardSocket, type ConnectionState } from './lib/socket';
import type { RuntimeConfig, Snapshot } from './lib/types';

const EMPTY_SNAPSHOT: Snapshot = {
    timestamp: 0,
    host: {
        cpu_percent: 0,
        memory_percent: 0,
        memory_used_gb: 0,
        memory_total_gb: 0,
        storage_percent: 0,
        storage_used_gb: 0,
        storage_total_gb: 0,
    },
    containers: [],
    runtime_name: 'Apple container',
    runtime_available: true,
    runtime_error: null,
};

const DEFAULT_CONFIG: RuntimeConfig = {
    runtime_name: 'Apple container',
    container_control_enabled: false,
    refresh_seconds: 3,
    logs_tail_default: 200,
};

export default function App() {
    const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY_SNAPSHOT);
    const [connection, setConnection] = useState<ConnectionState>('connecting');
    const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);

    useEffect(() => {
        fetch('/api/config')
            .then((resp) => resp.json())
            .then((data: RuntimeConfig) => setConfig(data))
            .catch(() => setConfig(DEFAULT_CONFIG));
    }, []);

    const socket = useMemo(() => new DashboardSocket(setSnapshot, setConnection), []);

    useEffect(() => {
        socket.start();
        return () => socket.stop();
    }, [socket]);

    const updatedAt = snapshot.timestamp > 0 ? new Date(snapshot.timestamp * 1000).toLocaleTimeString() : '--:--:--';

    return (
        <div className="app-shell">
            <header className="topbar">
                <div>
                    <h1>FruitSpy</h1>
                    <p>macOS host and container watch</p>
                </div>
                <div className="topbar-right">
                    <span className="runtime-pill">{config.runtime_name}</span>
                    <ConnectionIndicator state={connection} />
                    <span className="updated-at">Updated {updatedAt}</span>
                </div>
            </header>

            <main>
                <HostDashboard host={snapshot.host} />
                <PackageInventoryPanel host={snapshot.host} updatedAt={updatedAt} />
                <ContainerPanel
                    containers={snapshot.containers}
                    runtimeAvailable={snapshot.runtime_available}
                    runtimeError={snapshot.runtime_error}
                    runtimeName={snapshot.runtime_name}
                    controlEnabled={config.container_control_enabled}
                />
            </main>
        </div>
    );
}
