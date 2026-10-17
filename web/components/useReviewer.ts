"use client";

import { useEffect, useState } from "react";

const KEY = "mini-astr-reviewer";

/** The name is stored in the browser and written onto every search and review. */
export function useReviewer() {
  const [name, setName] = useState("");

  useEffect(() => {
    setName(window.localStorage.getItem(KEY) ?? "");
  }, []);

  function update(value: string) {
    setName(value);
    window.localStorage.setItem(KEY, value);
  }

  return { name, update };
}
