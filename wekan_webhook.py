from flask import Flask, request
from pymongo import MongoClient

from common import get_by_id, get_none


client = MongoClient()

# Card creation
# 
# {
#   text: '{{wekan-username}} added "{{card-title}}" to "{{list-name}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-createCard'
# }
# Card archival
# 
# {
#   text: '{{wekan-username}} archived "{{card-title}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-archivedCard'
# }
# Comment creation
# 
# {
#   text: '{{wekan-username}} commented on "{{card-title}}": "{{comment-body}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   boardId: '{{board-id}}',
#   comment: '{{comment-body}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-addComment'
# }
# Card move
# 
# {
#   text: '{{wekan-username}} moved "{{card-title}}" from "{{old-list-name}}" to "{{new-list-name}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{new-list-id}}',
#   oldListId: '{{old-list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-moveCard'
# }

app = Flask(__name__)

@app.route("/wekan", methods=['POST'])
def hello():
    print request
    print request.json

    # TODO check that request is json and correct or some stuff like that

    # card create -> we don't care about it

    # if card not linked to github, we don't care about it

    # card archival
    # * does that mean that we close the PR?
    # * do we have unarchival event?

    # comment creation
    # * not yet supported

    # card move -> interesting part
    # TODO: mark "[MILESTONE]" or something like that in columns titles
    # * if card move in another milestone than its one -> change of milestone
    # * if card is moved out of milestone keep its milestone

    # we don't have card modification like title or description?

    # do we have milestone modifications events?
    # apparently no :(

    client = MongoClient()

    if request.json["description"] == "act-moveCard":
        card_id = request.json["cardId"]
        card = get_by_id(client.wekan.cards, card_id)

        bridge = get_none(client.wekan.bridge_for_prs, {"wekan_id": card_id})

        print bridge
        print card

        if bridge is None:
            print "unhandled card", card_id
            return "unhandled card"

    return "ok"


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")