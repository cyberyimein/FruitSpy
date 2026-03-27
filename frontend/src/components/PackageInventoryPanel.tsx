import { useEffect, useMemo, useState } from 'react';
import type { HostMetrics, PackageInventory, PackageManagerInventory, PackageRecord } from '../lib/types';

type Props = {
    host: HostMetrics;
    updatedAt: string;
};

const MANAGER_LABELS: Record<string, string> = {
    npm: 'npm',
    brew: 'Homebrew',
    pip: 'pip',
    uv: 'uv',
};

export default function PackageInventoryPanel({ host, updatedAt }: Props) {
    const [inventory, setInventory] = useState<PackageInventory | null>(null);
    const [query, setQuery] = useState('');
    const [selectedManager, setSelectedManager] = useState('all');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isOpen, setIsOpen] = useState(false);
    const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

    async function loadInventory() {
        setLoading(true);
        setError(null);

        try {
            const response = await fetch('/api/packages');
            const contentType = response.headers.get('content-type') ?? '';
            const body = await response.text();

            if (!response.ok) {
                throw new Error(`Package inventory request failed: ${response.status}`);
            }

            if (contentType.includes('text/html') || looksLikeHtml(body)) {
                throw new Error(
                    'The backend returned the dashboard HTML instead of `/api/packages`. Restart FruitSpy so the updated backend is running, then refresh this page.',
                );
            }

            const payload = JSON.parse(body) as PackageInventory;
            setInventory(payload);
        } catch (err) {
            const message =
                err instanceof Error ? err.message : 'Failed to load package inventory. Please restart FruitSpy.';
            setError(message);
        } finally {
            setHasLoadedOnce(true);
            setLoading(false);
        }
    }

    useEffect(() => {
        if (!isOpen) {
            return;
        }

        const previousOverflow = document.body.style.overflow;
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setIsOpen(false);
            }
        };

        document.body.style.overflow = 'hidden';
        window.addEventListener('keydown', handleKeyDown);

        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [isOpen]);

    function openViewer() {
        setIsOpen(true);
        if (!hasLoadedOnce && !loading) {
            void loadInventory();
        }
    }

    const managers = inventory?.managers ?? [];
    const allPackages = useMemo(
        () => managers.flatMap((managerInventory) => managerInventory.packages),
        [managers],
    );

    const filteredPackages = useMemo(() => {
        const normalizedQuery = query.trim().toLowerCase();

        return allPackages.filter((pkg) => {
            if (selectedManager !== 'all' && pkg.manager !== selectedManager) {
                return false;
            }

            if (!normalizedQuery) {
                return true;
            }

            return [pkg.name, pkg.version, pkg.manager, pkg.source].some((field) =>
                field.toLowerCase().includes(normalizedQuery),
            );
        });
    }, [allPackages, query, selectedManager]);

    const availableManagers = managers.filter((manager) => manager.available).length;
    const unavailableManagers = managers.filter((manager) => !manager.available).length;
    const lastUpdated =
        inventory && inventory.timestamp > 0 ? new Date(inventory.timestamp * 1000).toLocaleTimeString() : '--:--:--';
    const overviewPackages = hasLoadedOnce ? String(inventory?.total_packages ?? 0) : 'On demand';
    const overviewManagers = hasLoadedOnce ? String(availableManagers) : '4 ready';
    const overviewUpdated = hasLoadedOnce ? lastUpdated : 'When opened';

    return (
        <>
            <section className="panel package-overview-panel">
                <div className="panel-head panel-head-split">
                    <div>
                        <h2>Package Inventory</h2>
                        <p>Package scanning is now on-demand, so the live dashboard stays fast until you open the viewer.</p>
                    </div>
                    <div className="package-panel-actions">
                        <button className="primary-btn" type="button" onClick={openViewer}>
                            Open Viewer
                        </button>
                    </div>
                </div>

                {error && hasLoadedOnce && <div className="panel-warning">Package inventory is unavailable: {error}</div>}

                <div className="package-overview-meta">
                    <div>
                        <strong>{overviewPackages}</strong>
                        <span>packages indexed</span>
                    </div>
                    <div>
                        <strong>{overviewManagers}</strong>
                        <span>managers ready</span>
                    </div>
                    <div>
                        <strong>{overviewUpdated}</strong>
                        <span>inventory updated</span>
                    </div>
                </div>

                {!hasLoadedOnce ? (
                    <div className="empty-card">Open the package viewer when you want to scan packages. It no longer runs on every main dashboard load.</div>
                ) : managers.length === 0 ? (
                    <div className="empty-card">The package viewer will appear here as soon as the backend reports package inventory.</div>
                ) : (
                    <div className="package-summary-grid package-summary-grid-compact">
                        {managers.map((manager) => (
                            <ManagerCard key={manager.manager} manager={manager} expanded={false} />
                        ))}
                    </div>
                )}
            </section>

            <div className={`subpage-shell ${isOpen ? 'subpage-shell-open' : ''}`} aria-hidden={!isOpen}>
                <button className="subpage-backdrop" type="button" aria-label="Close package viewer" onClick={() => setIsOpen(false)} />

                <section
                    className={`subpage-panel ${isOpen ? 'subpage-panel-open' : ''}`}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="package-viewer-title"
                >
                    <div className="subpage-header">
                        <div>
                            <div className="subpage-eyebrow">Animated subpage</div>
                            <h2 id="package-viewer-title">Installed Packages</h2>
                            <p>Search long package lists here without leaving the dashboard. Host metrics stay compact and containers stay out.</p>
                        </div>
                        <div className="subpage-actions">
                            <button
                                className="secondary-btn"
                                type="button"
                                onClick={() => void loadInventory()}
                                disabled={loading}
                            >
                                {loading ? 'Refreshing...' : 'Refresh'}
                            </button>
                            <button className="text-btn" type="button" onClick={() => setIsOpen(false)}>
                                Close
                            </button>
                        </div>
                    </div>

                    <div className="compact-host-grid">
                        <CompactHostMetric
                            title="CPU"
                            value={`${host.cpu_percent.toFixed(1)}%`}
                            note="Current processor load"
                        />
                        <CompactHostMetric
                            title="Memory"
                            value={`${host.memory_percent.toFixed(1)}%`}
                            note={`${host.memory_used_gb.toFixed(1)} / ${host.memory_total_gb.toFixed(1)} GB`}
                        />
                        <CompactHostMetric
                            title="Storage"
                            value={`${host.storage_percent.toFixed(1)}%`}
                            note={`${host.storage_used_gb.toFixed(1)} / ${host.storage_total_gb.toFixed(1)} GB`}
                        />
                        <CompactHostMetric title="Host Update" value={updatedAt} note="Live snapshot time" />
                    </div>

                    {error && hasLoadedOnce && <div className="panel-warning">Package inventory is unavailable: {error}</div>}

                    <div className="package-summary-grid package-summary-grid-expanded">
                        {managers.map((manager) => (
                            <ManagerCard key={manager.manager} manager={manager} expanded />
                        ))}
                    </div>

                    <div className="package-toolbar">
                        <label className="package-input-wrap">
                            <span>Search</span>
                            <input
                                className="package-search-input"
                                type="search"
                                value={query}
                                onChange={(event) => setQuery(event.target.value)}
                                placeholder="Search by package, version, manager, or source"
                            />
                        </label>

                        <label className="package-input-wrap">
                            <span>Manager</span>
                            <select
                                className="package-manager-select"
                                value={selectedManager}
                                onChange={(event) => setSelectedManager(event.target.value)}
                            >
                                <option value="all">All managers</option>
                                {managers.map((manager) => (
                                    <option key={manager.manager} value={manager.manager}>
                                        {MANAGER_LABELS[manager.manager] ?? manager.manager}
                                    </option>
                                ))}
                            </select>
                        </label>

                        <div className="package-results-summary">
                            <strong>{filteredPackages.length}</strong>
                            <span>
                                shown of {allPackages.length} package{allPackages.length === 1 ? '' : 's'}
                            </span>
                            <span>Inventory updated {lastUpdated}</span>
                            {unavailableManagers > 0 && (
                                <span>
                                    {unavailableManagers} manager{unavailableManagers === 1 ? '' : 's'} unavailable
                                </span>
                            )}
                        </div>
                    </div>

                    {loading && !inventory ? (
                        <div className="empty-card">Loading package inventory...</div>
                    ) : !hasLoadedOnce ? (
                        <div className="empty-card">Open this viewer to load package inventory on demand.</div>
                    ) : filteredPackages.length === 0 ? (
                        <div className="empty-card">
                            {allPackages.length === 0
                                ? 'No packages were reported by the available package managers.'
                                : 'No packages match the current search.'}
                        </div>
                    ) : (
                        <div className="package-list">
                            {filteredPackages.map((pkg) => (
                                <PackageRow key={buildPackageKey(pkg)} pkg={pkg} />
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </>
    );
}

function ManagerCard({
    manager,
    expanded,
}: {
    manager: PackageManagerInventory;
    expanded: boolean;
}) {
    return (
        <article className={`package-summary-card ${expanded ? 'package-summary-card-expanded' : ''}`}>
            <div className="package-summary-head">
                <h3>{MANAGER_LABELS[manager.manager] ?? manager.manager}</h3>
                <span className={`status-badge ${manager.available ? '' : 'status-badge-danger'}`}>
                    {manager.available ? `${manager.package_count} packages` : 'Unavailable'}
                </span>
            </div>

            {expanded ? (
                <p className="row-sub">Command: {manager.command ?? 'not found'}</p>
            ) : (
                <p className="row-sub">{collectSources(manager.packages) || 'No sources reported'}</p>
            )}

            {manager.error ? (
                <p className="package-manager-error">{manager.error}</p>
            ) : (
                <p className="package-summary-note">
                    {expanded ? `Sources: ${collectSources(manager.packages) || 'No packages reported'}` : 'Open the viewer to inspect package names and versions.'}
                </p>
            )}
        </article>
    );
}

function CompactHostMetric({
    title,
    value,
    note,
}: {
    title: string;
    value: string;
    note: string;
}) {
    return (
        <article className="compact-host-card">
            <span>{title}</span>
            <strong>{value}</strong>
            <p>{note}</p>
        </article>
    );
}

function PackageRow({ pkg }: { pkg: PackageRecord }) {
    return (
        <article className="package-row">
            <div>
                <div className="package-row-head">
                    <h3>{pkg.name}</h3>
                    <span className="status-badge">{MANAGER_LABELS[pkg.manager] ?? pkg.manager}</span>
                </div>
                <p className="row-sub">Source: {pkg.source}</p>
            </div>
            <div className="mini-metric">
                <span>Version</span>
                <strong>{pkg.version}</strong>
            </div>
            <div className="mini-metric">
                <span>Manager</span>
                <strong>{pkg.manager}</strong>
            </div>
        </article>
    );
}

function collectSources(packages: PackageRecord[]) {
    const sources = Array.from(new Set(packages.map((pkg) => pkg.source)));
    return sources.join(', ');
}

function buildPackageKey(pkg: PackageRecord) {
    return `${pkg.manager}:${pkg.source}:${pkg.name}:${pkg.version}`;
}

function looksLikeHtml(value: string) {
    const trimmed = value.trimStart().toLowerCase();
    return trimmed.startsWith('<!doctype html') || trimmed.startsWith('<html');
}
