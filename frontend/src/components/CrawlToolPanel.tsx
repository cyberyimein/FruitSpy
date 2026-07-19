import { FormEvent, useEffect, useState } from 'react';
import type { CrawlResult, CrawlToolStatus } from '../lib/types';

type ApiError = {
    error?: {
        code?: string;
        message?: string;
        retryable?: boolean;
    };
};

function formatBytes(value: number) {
    if (value >= 1024 * 1024) {
        return `${(value / (1024 * 1024)).toFixed(value % (1024 * 1024) === 0 ? 0 : 1)} MiB`;
    }
    return `${Math.round(value / 1024)} KiB`;
}

export default function CrawlToolPanel() {
    const [status, setStatus] = useState<CrawlToolStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [changing, setChanging] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [url, setUrl] = useState('https://example.com/');
    const [timeoutMs, setTimeoutMs] = useState(30000);
    const [testing, setTesting] = useState(false);
    const [testError, setTestError] = useState<string | null>(null);
    const [result, setResult] = useState<CrawlResult | null>(null);
    const [copied, setCopied] = useState(false);

    async function loadStatus(background = false) {
        if (!background) {
            setLoading(true);
        }
        try {
            const response = await fetch('/api/v1/tools/crawl/status');
            if (!response.ok) {
                throw new Error(`Crawl4AI status request failed: ${response.status}`);
            }
            setStatus((await response.json()) as CrawlToolStatus);
            setError(null);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : 'Unable to load Crawl4AI status');
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
            const response = await fetch('/api/v1/tools/crawl/enabled', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-FruitSpy-Control': '1',
                },
                body: JSON.stringify({ enabled: !status.enabled }),
            });
            const payload = (await response.json()) as CrawlToolStatus & ApiError;
            if (!response.ok) {
                throw new Error(payload.error?.message ?? `Crawl4AI update failed: ${response.status}`);
            }
            setStatus(payload);
        } catch (updateError) {
            setError(updateError instanceof Error ? updateError.message : 'Unable to update Crawl4AI');
        } finally {
            setChanging(false);
        }
    }

    async function runTest(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!status?.ready || testing) {
            return;
        }
        setTesting(true);
        setTestError(null);
        setResult(null);
        setCopied(false);
        try {
            const response = await fetch('/api/v1/tools/crawl/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-FruitSpy-Control': '1',
                },
                body: JSON.stringify({
                    url: url.trim(),
                    timeout_ms: timeoutMs,
                }),
            });
            const payload = (await response.json()) as CrawlResult & ApiError;
            if (!response.ok) {
                const code = payload.error?.code ? `${payload.error.code}: ` : '';
                throw new Error(`${code}${payload.error?.message ?? `Crawl test failed: ${response.status}`}`);
            }
            setResult(payload);
            void loadStatus(true);
        } catch (runError) {
            setTestError(runError instanceof Error ? runError.message : 'Unable to run Crawl4AI test');
        } finally {
            setTesting(false);
        }
    }

    async function copyMarkdown() {
        if (!result) {
            return;
        }
        try {
            await navigator.clipboard.writeText(result.markdown);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
        } catch {
            setTestError('Unable to copy Markdown to the clipboard');
        }
    }

    if (loading && !status) {
        return <div className="empty-card">Loading Crawl4AI status...</div>;
    }

    if (!status) {
        return (
            <section className="panel">
                <div className="panel-warning">{error ?? 'Crawl4AI status is unavailable.'}</div>
            </section>
        );
    }

    const isTransitioning = changing || status.state === 'checking' || status.state === 'disabling';
    const statusIsDanger = status.state === 'degraded';

    return (
        <section className="panel">
            <article className="python-tool-card crawl-tool-card">
                <div className="python-tool-head">
                    <div>
                        <div className="row-title-wrap">
                            <h2>Crawl4AI</h2>
                            <span className={`status-badge ${statusIsDanger ? 'status-badge-danger' : ''}`}>
                                {status.state}
                            </span>
                        </div>
                        <p>
                            Renders public web pages in Chromium and returns sanitized Markdown to Anomalo.
                            Private networks, unsafe protocols, oversized responses and redirect abuse are blocked.
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
                                : status.state === 'disabling'
                                    ? 'Disabling...'
                                    : status.enabled
                                        ? 'Disable'
                                        : 'Enable'}
                    </button>
                </div>

                {(error || status.error) && <div className="panel-warning">{error ?? status.error}</div>}

                <div className="python-tool-metrics crawl-tool-metrics">
                    <div>
                        <span>Workload</span>
                        <strong>{status.running_executions} active · {status.queued_executions} queued</strong>
                    </div>
                    <div>
                        <span>Capacity</span>
                        <strong>{status.limits.max_concurrency} concurrent · {status.limits.max_queue} queued</strong>
                    </div>
                    <div>
                        <span>Timeout</span>
                        <strong>{status.limits.timeout_ms / 1000}s default · {status.limits.max_timeout_ms / 1000}s max</strong>
                    </div>
                    <div>
                        <span>Authentication</span>
                        <strong>{status.authentication_configured ? 'Bearer configured' : 'Optional / not configured'}</strong>
                    </div>
                    <div>
                        <span>Content limits</span>
                        <strong>{formatBytes(status.limits.max_html_bytes)} HTML · {formatBytes(status.limits.max_response_bytes)} JSON</strong>
                    </div>
                    <div>
                        <span>Redirect limit</span>
                        <strong>{status.limits.max_redirects} hops</strong>
                    </div>
                </div>

                <div className="crawl-test">
                    <div className="crawl-test-head">
                        <div>
                            <span className="crawl-test-label">Dashboard test</span>
                            <p>Run a real crawl without exposing the configured API token to this browser.</p>
                        </div>
                    </div>
                    <form className="crawl-test-form" onSubmit={(event) => void runTest(event)}>
                        <label className="crawl-field crawl-url-field">
                            <span>Public URL</span>
                            <input
                                type="url"
                                value={url}
                                onChange={(event) => setUrl(event.target.value)}
                                placeholder="https://example.com/"
                                required
                                maxLength={4096}
                            />
                        </label>
                        <label className="crawl-field">
                            <span>Timeout (ms)</span>
                            <input
                                type="number"
                                value={timeoutMs}
                                onChange={(event) => setTimeoutMs(Number(event.target.value))}
                                min={1000}
                                max={status.limits.max_timeout_ms}
                                step={1000}
                                required
                            />
                        </label>
                        <button className="primary-btn" type="submit" disabled={!status.ready || testing}>
                            {testing ? 'Crawling...' : 'Run Test'}
                        </button>
                    </form>

                    {testError && <div className="panel-warning">{testError}</div>}

                    {result && (
                        <div className="crawl-result">
                            <div className="crawl-result-summary">
                                <div>
                                    <span>HTTP</span>
                                    <strong>{result.status_code}</strong>
                                </div>
                                <div>
                                    <span>Total</span>
                                    <strong>{result.timings.total_ms} ms</strong>
                                </div>
                                <div>
                                    <span>Rendered</span>
                                    <strong>{result.rendered ? 'Yes' : 'No'}</strong>
                                </div>
                                <div>
                                    <span>Markdown</span>
                                    <strong>{result.metrics.markdown_chars.toLocaleString()} chars</strong>
                                </div>
                            </div>
                            <div className="crawl-result-meta">
                                <span>{result.title || 'Untitled page'}</span>
                                <a href={result.final_url} target="_blank" rel="noreferrer">{result.final_url}</a>
                            </div>
                            <div className="crawl-markdown-head">
                                <strong>Markdown output</strong>
                                <button className="secondary-btn" type="button" onClick={() => void copyMarkdown()}>
                                    {copied ? 'Copied' : 'Copy Markdown'}
                                </button>
                            </div>
                            <pre className="crawl-markdown">{result.markdown}</pre>
                            {result.warnings.length > 0 && (
                                <small className="crawl-warning">{result.warnings.join(' ')}</small>
                            )}
                        </div>
                    )}
                </div>
            </article>
        </section>
    );
}
