import type { ConnectionState } from '../lib/socket';

type Props = {
    state: ConnectionState;
};

const LABELS: Record<ConnectionState, string> = {
    connecting: 'Connecting',
    online: 'Live',
    reconnecting: 'Reconnecting',
    offline: 'Offline',
};

export default function ConnectionIndicator({ state }: Props) {
    return (
        <div className={`connection-pill state-${state}`}>
            <span className="connection-dot" />
            <span>{LABELS[state]}</span>
        </div>
    );
}
