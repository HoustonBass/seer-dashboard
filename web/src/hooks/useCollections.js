import { useState } from "react";
import { fetchCollection } from "../lib/api";

// Lazily loads collections as they're opened and keeps them for the life of
// the view: {[collectionId]: {status: "loading"|"error"|"ready", collection}}.
export default function useCollections() {
  const [byId, setById] = useState({});

  function load(collectionId) {
    if (byId[collectionId]) return;
    setById((prev) => ({ ...prev, [collectionId]: { status: "loading" } }));
    fetchCollection(collectionId)
      .then((collection) => setById((prev) => ({ ...prev, [collectionId]: { status: "ready", collection } })))
      .catch(() => setById((prev) => ({ ...prev, [collectionId]: { status: "error" } })));
  }

  function retry(collectionId) {
    setById((prev) => {
      const { [collectionId]: _dropped, ...rest } = prev;
      return rest;
    });
  }

  return { byId, load, retry };
}
