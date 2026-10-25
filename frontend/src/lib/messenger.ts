import { createContext, useContext } from "react";
import type { ChatPerson } from "./api";
export const MessengerContext = createContext<(person: ChatPerson) => void>(() => {});
export const useMessenger = () => useContext(MessengerContext);
