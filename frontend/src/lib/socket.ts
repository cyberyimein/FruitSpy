import type { Snapshot } from './types';

export type ConnectionState = 'connecting' | 'online' | 'reconnecting' | 'offline';

type SnapshotHandler = (snapshot: Snapshot) => void;
type StateHandler = (state: ConnectionState) => void;

export class DashboardSocket {
    private ws: WebSocket | null = null;
    private shouldRun = true;
    private reconnectTimer: number | null = null;

    constructor(
        private readonly onSnapshot: SnapshotHandler,
        private readonly onState: StateHandler,
    ) { }

    start() {
        this.shouldRun = true;
        this.connect();
    }

    stop() {
        this.shouldRun = false;
        if (this.reconnectTimer) {
            window.clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.ws?.close();
        this.ws = null;
    }

    private connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${protocol}://${window.location.host}/ws/dashboard`;

        this.onState(this.ws ? 'reconnecting' : 'connecting');
        this.ws = new WebSocket(url);

        this.ws.onopen = () => this.onState('online');

        this.ws.onmessage = (event) => {
            try {
                this.onSnapshot(JSON.parse(event.data) as Snapshot);
            } catch {
                // Ignore malformed frames to keep UI responsive.
            }
        };

        this.ws.onclose = () => {
            if (!this.shouldRun) {
                this.onState('offline');
                return;
            }
            this.onState('reconnecting');
            this.reconnectTimer = window.setTimeout(() => this.connect(), 1200);
        };

        this.ws.onerror = () => {
            this.ws?.close();
        };
    }
}
