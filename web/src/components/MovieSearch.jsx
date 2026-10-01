import { Fragment, useState } from "react";
import useCollections from "../hooks/useCollections";
import useMovieRequests from "../hooks/useMovieRequests";
import useMovieSearch from "../hooks/useMovieSearch";
import { MOVIE_STATE_PILL, movieState, summarizeStates } from "../lib/movieState";

// "Find movies": search Overseerr for any movie, see which collection each
// hit belongs to, and open that collection to see every movie in it (not
// just the ones requested) with each one's Overseerr state. Presentational
// plus two hooks — all fetching lives in hooks/useMovieSearch.js and
// hooks/useCollections.js.
export default function MovieSearch() {
  const [query, setQuery] = useState("");
  const [openCollectionId, setOpenCollectionId] = useState(null);
  const { results, error, loading, searchable } = useMovieSearch(query);
  const collections = useCollections();
  const requests = useMovieRequests();

  function toggleCollection(id) {
    const next = openCollectionId === id ? null : id;
    setOpenCollectionId(next);
    if (next) collections.load(next);
  }

  return (
    <div className="bg-[var(--surface)] min-h-[60vh]">
      <div className="px-5 py-4 border-b border-[var(--rule)]">
        <input
          type="search"
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for a movie…"
          aria-label="Search for a movie"
          className="w-full max-w-xl rounded border border-[var(--rule-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
      </div>

      {!searchable && <p className="p-5 text-sm text-[var(--text-faint)]">Type a movie title to search Overseerr.</p>}
      {loading && <p className="p-5 text-sm text-[var(--text-faint)]">Searching…</p>}
      {error && <p className="p-5 text-sm text-[var(--accent)]">Search failed — {error}. Try again.</p>}
      {results?.length === 0 && (
        <p className="p-5 text-sm text-[var(--text-faint)]">
          No movies match <span className="font-semibold text-[var(--text)]">"{query.trim()}"</span>.
        </p>
      )}

      {results?.map((m) => {
        const open = m.collection && openCollectionId === m.collection.id;
        return (
          <Fragment key={m.tmdb_id}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3 border-b border-[var(--rule)]">
              <Poster path={m.poster_path} />
              <div className="flex-1 basis-48 min-w-0">
                <div className="font-semibold text-sm truncate">
                  {m.title}
                  {m.release_date && <span className="text-[var(--text-faint)] font-normal"> ({m.release_date.slice(0, 4)})</span>}
                </div>
                {m.collection ? (
                  <button
                    type="button"
                    onClick={() => toggleCollection(m.collection.id)}
                    aria-expanded={open}
                    className="mt-1 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--primary)] hover:underline text-left"
                  >
                    {m.collection.name}
                    <span aria-hidden="true" className={`mono text-[10px] transition-transform ${open ? "" : "-rotate-90"}`}>
                      ▾
                    </span>
                  </button>
                ) : (
                  <div className="text-xs text-[var(--text-faint)] mt-0.5">Not part of a collection</div>
                )}
                <RequestError message={requests.errorOf(m.tmdb_id)} />
              </div>
              <StatePill
                mediaStatus={requests.statusOf(m.tmdb_id, m.media_status)}
                pending={requests.isPending(m.tmdb_id)}
                onRequest={() => requests.request(m.tmdb_id)}
                title={m.title}
              />
            </div>
            {open && (
              <CollectionCard
                entry={collections.byId[m.collection.id]}
                currentId={m.tmdb_id}
                requests={requests}
                onRetry={() => collections.retry(m.collection.id)}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

// One slot for a movie's state. Not requested is itself the action — a
// "Request" pill — so it turns into Requesting… and then Requested in
// place, with nothing shifting around it.
function StatePill({ mediaStatus, pending, onRequest, title }) {
  const { key, label } = movieState(mediaStatus);
  const base = "inline-flex items-center justify-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap sm:min-w-[8.5rem]";
  if (pending) {
    return <span className={`${base} text-[var(--pending)] bg-[var(--pending-bg)]`}>Requesting…</span>;
  }
  if (key === "not_requested") {
    return (
      <button
        type="button"
        onClick={onRequest}
        aria-label={`Request ${title}`}
        className={`${base} border border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-[var(--primary-contrast)]`}
      >
        + Request
      </button>
    );
  }
  return (
    <span className={`${base} ${MOVIE_STATE_PILL[key]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

function RequestError({ message }) {
  return message ? <div className="text-xs text-[var(--accent)] mt-1">Couldn't request — {message}</div> : null;
}

function Poster({ path }) {
  return path ? (
    <img src={`https://image.tmdb.org/t/p/w92${path}`} alt="" loading="lazy" className="w-9 h-[54px] object-cover rounded-sm bg-[var(--unmatched-bg)]" />
  ) : (
    <span aria-hidden="true" className="w-9 h-[54px] rounded-sm bg-[var(--unmatched-bg)]" />
  );
}

// The whole collection, in release order, with the searched movie marked.
function CollectionCard({ entry, currentId, requests, onRetry }) {
  const [confirming, setConfirming] = useState(false);

  if (!entry || entry.status === "loading") {
    return <p className="px-5 py-3 text-sm text-[var(--text-faint)] border-b border-[var(--rule)]">Loading collection…</p>;
  }
  if (entry.status === "error") {
    return (
      <p className="px-5 py-3 text-sm text-[var(--accent)] border-b border-[var(--rule)]">
        Couldn't load this collection.{" "}
        <button onClick={onRetry} className="font-semibold underline">
          Try again
        </button>
      </p>
    );
  }

  const { collection } = entry;
  const parts = collection.parts.map((p) => ({ ...p, media_status: requests.statusOf(p.tmdb_id, p.media_status) }));
  const missing = parts.filter((p) => movieState(p.media_status).key === "not_requested");
  const busy = parts.some((p) => requests.isPending(p.tmdb_id));
  const result = requests.collectionResultOf(collection.id);

  function confirmRequestAll() {
    setConfirming(false);
    requests.requestAll(collection.id, missing.map((p) => p.tmdb_id));
  }

  return (
    <section className="mx-2 sm:mx-3.5 my-3.5 border border-[var(--rule-strong)] bg-[var(--surface)]">
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2 px-5 py-3 border-b border-[var(--rule)]">
        <span className="flex-1 basis-40 min-w-0 text-lg leading-tight text-balance" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
          {collection.name}
        </span>
        <span className="mono text-xs text-[var(--text-muted)]">{summarizeStates(parts)}</span>
        {missing.length > 0 &&
          !busy &&
          (confirming ? (
            <span className="flex items-center gap-1.5 text-xs">
              <span className="text-[var(--text-muted)]">
                Request {missing.length} {missing.length === 1 ? "movie" : "movies"}?
              </span>
              <button
                type="button"
                onClick={confirmRequestAll}
                className="px-2.5 py-1 rounded-full font-semibold bg-[var(--primary)] text-[var(--primary-contrast)]"
              >
                Confirm
              </button>
              <button type="button" onClick={() => setConfirming(false)} className="px-2 py-1 text-[var(--text-muted)] hover:underline">
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="text-xs font-semibold px-2.5 py-1 rounded-full border border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-[var(--primary-contrast)]"
            >
              Request all {missing.length}
            </button>
          ))}
        {busy && <span className="text-xs font-semibold text-[var(--pending)]">Requesting…</span>}
      </div>
      {result && (
        <p className={`px-5 py-2 text-xs border-b border-[var(--rule)] ${result.error || result.failed ? "text-[var(--accent)]" : "text-[var(--available)]"}`}>
          {result.error
            ? `Couldn't request this collection — ${result.error}.`
            : `Requested ${result.requested} ${result.requested === 1 ? "movie" : "movies"}.${result.failed ? ` ${result.failed} failed — see below.` : ""}`}
        </p>
      )}
      <div className="[&>*:last-child]:border-b-0">
        {parts.map((p) => (
          <div
            key={p.tmdb_id}
            className={`flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3 border-b border-[var(--rule)] ${
              p.tmdb_id === currentId ? "bg-[var(--surface-raised)] shadow-[inset_3px_0_0_var(--accent)]" : ""
            }`}
          >
            <div className="flex-1 basis-48 min-w-0 text-sm">
              <div className="truncate">
                <span className={p.tmdb_id === currentId ? "font-semibold" : ""}>{p.title}</span>
                {p.release_date && <span className="text-[var(--text-faint)]"> ({p.release_date.slice(0, 4)})</span>}
              </div>
              <RequestError message={requests.errorOf(p.tmdb_id)} />
            </div>
            <StatePill
              mediaStatus={p.media_status}
              pending={requests.isPending(p.tmdb_id)}
              onRequest={() => requests.request(p.tmdb_id)}
              title={p.title}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
