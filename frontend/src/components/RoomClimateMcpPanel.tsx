import { useEffect, useState } from 'react';
import type { RoomClimateMcpStatus } from '../lib/types';

type ProtocolMode = RoomClimateMcpStatus['protocol_mode'];

export default function RoomClimateMcpPanel() {
    const [status, setStatus] = useState<RoomClimateMcpStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [changing, setChanging] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    async function loadStatus(background = false) {
        if (!background) {
            setLoading(true);
        }
        try {
            const response = await fetch('/api/v1/tools/room-climate');
            if (!response.ok) {
                throw new Error(`Room Climate MCP status request failed: ${response.status}`);
            }
            setStatus((await response.json()) as RoomClimateMcpStatus);
            setError(null);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : 'Unable to load Room Climate MCP');
        } finally {
            if (!background) {
                setLoading(false);
            }
        }
    }

    useEffect(() => {
        void loadStatus();
        const timer = window.setInterval(() => void loadStatus(true), 5000);
        return () => window.clearInterval(timer);
    }, []);

    async function selectMode(mode: ProtocolMode) {
        if (!status || changing || mode === status.protocol_mode) {
            return;
        }
        setChanging(true);
        setError(null);
        try {
            const response = await fetch('/api/v1/tools/room-climate/protocol-mode', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-FruitSpy-Control': '1',
                },
                body: JSON.stringify({ protocol_mode: mode }),
            });
            const payload = await response.json() as RoomClimateMcpStatus & {
                error?: { message?: string };
            };
            if (!response.ok) {
                throw new Error(payload.error?.message ?? `Protocol update failed: ${response.status}`);
            }
            setStatus(payload);
        } catch (updateError) {
            setError(updateError instanceof Error ? updateError.message : 'Unable to update MCP protocol');
        } finally {
            setChanging(false);
        }
    }

    async function copyEndpoint() {
        if (!status) {
            return;
        }
        try {
            await navigator.clipboard.writeText(`${window.location.origin}${status.endpoint}`);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
        } catch {
            setError('Unable to copy the MCP endpoint');
        }
    }

    if (loading && !status) {
        return <div className="empty-card">Loading Room Climate MCP...</div>;
    }
    if (!status) {
        return (
            <section className="panel">
                <div className="panel-warning">{error ?? 'Room Climate MCP is unavailable.'}</div>
            </section>
        );
    }

    return (
        <section className="panel">
            <article className="python-tool-card room-mcp-card">
                <div className="python-tool-head">
                    <div>
                        <div className="row-title-wrap">
                            <h2>Room Climate MCP</h2>
                            <span className={`status-badge ${status.climate.stale ? 'status-badge-danger' : ''}`}>
                                {status.climate.state}
                            </span>
                        </div>
                        <p>
                            Exposes the latest local temperature, humidity and CO₂ reading through the
                            read-only <code>{status.tool_name}</code> MCP tool.
                        </p>
                    </div>
                    <button className="secondary-btn" type="button" onClick={() => void copyEndpoint()}>
                        {copied ? 'Copied' : 'Copy endpoint'}
                    </button>
                </div>

                {error && <div className="panel-warning">{error}</div>}

                <div className="protocol-selector-block">
                    <div>
                        <span className="crawl-test-label">Protocol mode</span>
                        <p>Switching changes the actual MCP lifecycle and wire format for this endpoint.</p>
                    </div>
                    <div className="protocol-segmented" role="group" aria-label="MCP protocol mode">
                        <button
                            type="button"
                            className={status.protocol_mode === 'modern' ? 'active' : ''}
                            onClick={() => void selectMode('modern')}
                            disabled={changing}
                        >
                            <strong>New</strong>
                            <span>2026-07-28</span>
                        </button>
                        <button
                            type="button"
                            className={status.protocol_mode === 'legacy' ? 'active' : ''}
                            onClick={() => void selectMode('legacy')}
                            disabled={changing}
                        >
                            <strong>Compatible</strong>
                            <span>2025-11-25</span>
                        </button>
                    </div>
                </div>

                <div className="python-tool-metrics room-mcp-metrics">
                    <div>
                        <span>Active protocol</span>
                        <strong>{status.protocol_version}</strong>
                    </div>
                    <div>
                        <span>Tool</span>
                        <strong>{status.tool_name}</strong>
                    </div>
                    <div>
                        <span>Endpoint</span>
                        <strong>{status.endpoint}</strong>
                    </div>
                    <div>
                        <span>Authentication</span>
                        <strong>{status.authentication_configured ? 'Bearer configured' : 'Not configured'}</strong>
                    </div>
                </div>

                <div className="python-tool-foot">
                    <span>Storage</span>
                    <strong>Latest reading only · no history</strong>
                    <small>
                        5 minute sampling · 45 second BLE receive window · read-only MCP tool
                    </small>
                </div>
            </article>
        </section>
    );
}
