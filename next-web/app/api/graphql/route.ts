import { ApolloServer } from "@apollo/server";
import { startServerAndCreateNextHandler } from "@as-integrations/next/dist";
import { gql } from "graphql-tag";
import { NextRequest } from "next/server";

const isDemoMode = process.env.DEMO_MODE === "true";
const { search, resourceByHash, statsInfo, latestResources, randomResources } =
  isDemoMode ? require("./moke") : require("./service");

if (isDemoMode) {
  console.log("[SehuaTang-Search] This website is running in demo mode.");
}

const typeDefs = gql`
  type Ed2kResourceFile {
    index: Int
    path: String
    extension: String
    size: String
  }

  type Ed2kResource {
    hash: String!
    name: String!
    title: String
    description: String
    source_url: String
    board_fid: String
    board_name: String
    forum_id: String
    forum_name: String
    extract_password: String
    preview_images: [String!]
    ed2k_links: [String!]
    size: String!
    ed2k_link: String!
    link_kind: String
    single_file: Boolean!
    files_count: Int!
    files: [Ed2kResourceFile!]!
    created_at: Int!
    updated_at: Int!
  }

  input SearchQueryInput {
    keyword: String!
    offset: Int!
    limit: Int!
    sortType: String
    filterTime: String
    filterSize: String
    matchMode: String
    fuzzy: Boolean
    withTotalCount: Boolean
  }

  type SearchResult {
    keywords: [String!]!
    resources: [Ed2kResource!]!
    total_count: Int!
    has_more: Boolean!
  }

  type statsInfoResult {
    size: String!
    total_count: Int!
    updated_at: Int!
    latest_resource_hash: String
    latest_resource: Ed2kResource
  }

  type Query {
    search(queryInput: SearchQueryInput!): SearchResult!
    resourceByHash(hash: String!): Ed2kResource
    statsInfo: statsInfoResult
    latestResources(limit: Int): [Ed2kResource!]!
    randomResources(limit: Int): [Ed2kResource!]!
  }
`;

const server = new ApolloServer({
  typeDefs,
  resolvers: {
    Query: {
      search,
      resourceByHash,
      statsInfo,
      latestResources,
      randomResources,
    },
  },
});

const handler = startServerAndCreateNextHandler<NextRequest>(server, {
  context: async (req) => ({ req }),
});

export { handler as GET, handler as POST };
