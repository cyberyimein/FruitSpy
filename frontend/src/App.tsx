import { useEffect, useMemo, useState } from 'react';
import ConnectionIndicator from './components/ConnectionIndicator';
import ContainerPanel from './components/ContainerPanel';
import HostDashboard from './components/HostDashboard';
import PackageInventoryPanel from './components/PackageInventoryPanel';
import { DashboardSocket, type ConnectionState } from './lib/socket';
import type { RuntimeConfig, Snapshot } from './lib/types';

const PAGE_KEYS = ['host', 'packages', 'containers', 'api'] as const;
type PageKey = (typeof PAGE_KEYS)[number];

const NAV_ITEMS: Array<{ key: PageKey; label: string }> = [
    { key: 'host', label: 'Host' },
    { key: 'packages', label: 'Packages' },
    { key: 'containers', label: 'Containers' },
    { key: 'api', label: 'API' },
];

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

function getPageFromHash(): PageKey {
    const hash = window.location.hash.replace('#', '');
    return PAGE_KEYS.includes(hash as PageKey) ? (hash as PageKey) : 'host';
}

export default function App() {
    const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY_SNAPSHOT);
    const [connection, setConnection] = useState<ConnectionState>('connecting');
    const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);
    const [activePage, setActivePage] = useState<PageKey>(() => getPageFromHash());

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

    useEffect(() => {
        function syncPageFromLocation() {
            setActivePage(getPageFromHash());
        }

        window.addEventListener('hashchange', syncPageFromLocation);
        window.addEventListener('popstate', syncPageFromLocation);
        return () => {
            window.removeEventListener('hashchange', syncPageFromLocation);
            window.removeEventListener('popstate', syncPageFromLocation);
        };
    }, []);

    const updatedAt = snapshot.timestamp > 0 ? new Date(snapshot.timestamp * 1000).toLocaleTimeString() : '--:--:--';
    const runningContainers = snapshot.containers.filter((container) => container.status === 'running').length;
    const totalContainers = snapshot.containers.length;

    function selectPage(page: PageKey) {
        setActivePage(page);
        if (window.location.hash !== `#${page}`) {
            window.history.pushState(null, '', `#${page}`);
        }
    }

    return (
        <div className="app-shell">
            <header className="topbar">
                <button className="brand" type="button" onClick={() => selectPage('host')} aria-label="FruitSpy host page">
                    <span className="brand-copy">
                        <strong>FruitSpy</strong>
                        <span>Host console</span>
                    </span>
                </button>
                <nav className="app-nav" aria-label="Dashboard pages">
                    {NAV_ITEMS.map((item) => (
                        <button
                            key={item.key}
                            className={`nav-tab ${activePage === item.key ? 'active' : ''}`}
                            type="button"
                            onClick={() => selectPage(item.key)}
                            aria-current={activePage === item.key ? 'page' : undefined}
                        >
                            {item.label}
                        </button>
                    ))}
                </nav>
                <div className="topbar-right">
                    <span className="runtime-pill">{config.runtime_name}</span>
                    <ConnectionIndicator state={connection} />
                    <span className="header-stat">
                        <strong>{runningContainers}/{totalContainers}</strong>
                        <span>containers</span>
                    </span>
                    <span className="header-stat">
                        <strong>{config.refresh_seconds}s</strong>
                        <span>refresh</span>
                    </span>
                    <span className="header-stat">
                        <strong>{updatedAt}</strong>
                        <span>updated</span>
                    </span>
                </div>
            </header>

            <main className="dashboard-main">
                <PageHero page={activePage} />

                {activePage === 'host' && <HostDashboard host={snapshot.host} />}
                {activePage === 'packages' && <PackageInventoryPanel host={snapshot.host} updatedAt={updatedAt} />}
                {activePage === 'containers' && (
                    <ContainerPanel
                        containers={snapshot.containers}
                        runtimeAvailable={snapshot.runtime_available}
                        runtimeError={snapshot.runtime_error}
                        runtimeName={snapshot.runtime_name}
                        controlEnabled={config.container_control_enabled}
                    />
                )}
            </main>
        </div>
    );
}

function PageHero({
    page,
}: {
    page: PageKey;
}) {
    const copy: Record<PageKey, { eyebrow: string; title: string }> = {
        host: { eyebrow: 'Live monitor', title: 'Host' },
        packages: { eyebrow: 'Inventory', title: 'Packages' },
        containers: { eyebrow: 'Runtime monitor', title: 'Containers' },
        api: { eyebrow: 'Planned relay', title: 'AI API Relay' },
    };

    return (
        <section className="command-strip" aria-label={`${copy[page].title} page`}>
            <div className="command-copy">
                <span className="eyebrow">{copy[page].eyebrow}</span>
                <h1>{copy[page].title}</h1>
            </div>
        </section>
    );
}
